from odoo import models, fields, api
from datetime import datetime
from datetime import timedelta

import logging
import pytz

_logger = logging.getLogger(__name__)


class OpportunityWizard(models.TransientModel):
    _name = 'opportunity.wizard'
    _description = 'Opportunity Wizard'

    name = fields.Char(string="Opportunity Name", required=True)
    brand_id = fields.Many2one('res.brand', string="Brand", required=False)
    brand_id2 = fields.Many2many('res.brand', string="Brand(s)", required=False)
    brand_used_id = fields.Many2many(
        'res.brand',
        'opportunity_wizard_used_brand_rel',
        'wizard_id',
        'brand_id',
        string="Used Brand(s)"
    )
    opportunity_type = fields.Selection([
        ('new', 'New'),
        ('trade_in', 'Trade In'),
        ('used', 'Used'),
        ('service', 'Service'),
    ], string='Opportunity Type', tracking=True,default='new')
    sub_brand_id = fields.Many2one('res.sub.brand', string="Sub Brand", required=False)
    sub_brand_id2 = fields.Many2many('res.sub.brand', string="Sub Brand(s)", required=False)
    sub_brand_used_id = fields.Many2many(
        'res.sub.brand',
        'opportunity_wizard_used_sub_brand_rel',
        'wizard_id',
        'sub_brand_id',
        string="Used Sub Brand(s)"
    )
    area_id = fields.Many2one('res.area', string="Area",required=True)
    branch_id = fields.Many2one('res.branch', string="Branch",required=True)
    source_id = fields.Many2one('res.source', string="Source", required=True)
    sla_duration = fields.Float(string="SLA Duration")
    partner_id = fields.Many2one('res.partner', string="Customer")
    marketing_offer = fields.Many2one('marketing.offers', string='Marketing Offer')
    call_type = fields.Many2one('call.type', string='Call Type', required=True)
    model = fields.Char(string="Model")
    kilometers = fields.Char(string="Kilometers")
    service_id = fields.Many2one('res.service', string='Service')

    @api.model
    def default_get(self, fields):
        """Pre-fill area and branch from the selected customer"""
        res = super().default_get(fields)
        partner = self.env['res.partner'].browse(self.env.context.get('active_id'))
        if partner:
            res['partner_id'] = partner.id
            res['name'] = partner.name
            res['area_id'] = partner.area_id.id
            res['branch_id'] = partner.branch_id.id
            res['source_id'] = partner.crm_source_id.id
        return res

    @api.onchange('brand_id2')
    def _onchange_brand_id2(self):
        """Clear sub-brands when brands change (New section)"""
        if self.brand_id2:
            # Keep only sub-brands that belong to selected brands
            valid_sub_brands = self.sub_brand_id2.filtered(lambda sb: sb.brand in self.brand_id2)
            self.sub_brand_id2 = valid_sub_brands
        else:
            # If no brands selected, clear all sub-brands
            self.sub_brand_id2 = False

    @api.onchange('brand_used_id')
    def _onchange_brand_used_id(self):
        """Clear sub-brands when brands change (Used section)"""
        if self.brand_used_id:
            # Keep only sub-brands that belong to selected brands
            valid_sub_brands = self.sub_brand_used_id.filtered(lambda sb: sb.brand in self.brand_used_id)
            self.sub_brand_used_id = valid_sub_brands
        else:
            # If no brands selected, clear all sub-brands
            self.sub_brand_used_id = False

    #################################################################################

    def _get_next_salesperson(self):
        """Determine the next salesperson for the selected branch (Round Robin per Branch + Shift)."""
        self.ensure_one()
        branch = self.branch_id
        if not branch:
            _logger.info("No branch selected in wizard. Exiting _get_next_salesperson.")
            return False

        # 1) Get branch sales teams
        sales_teams = self.env['crm.team'].search([('branch_name', '=', branch.id)])
        if not sales_teams:
            _logger.info("No sales teams found for branch %s.", branch.branch_name)
            return False

        # 2) Active team members
        active_members = self.env['crm.team.member'].search([
            ('crm_team_id', 'in', sales_teams.ids),
            ('state', '=', 'active')
        ])

        _logger.info("Found %d active team member(s) in branch %s.",
                     len(active_members), branch.branch_name)

        if not active_members:
            return False

        # 3) Get Egypt local time
        utc_now = fields.Datetime.now()
        egypt_tz = pytz.timezone('Africa/Cairo')
        local_now = utc_now.replace(tzinfo=pytz.utc).astimezone(egypt_tz)
        current_hour = local_now.hour + local_now.minute / 60.0

        _logger.info("Current Egypt hour: %.4f", current_hour)

        # 4) Filter sequences by current shift
        shift_filtered_domain = [
            ('branch', '=', branch.id),
            ('state', '=', 'active'),
            ('sales_person', 'in', active_members.mapped('user_id').ids),
            ('shift.from_date', '<=', current_hour),
            ('shift.to_date', '>=', current_hour),
        ]

        sequences = self.env['distribute.sequence'].search(
            shift_filtered_domain,
            order='sequence asc, id asc'
        )

        if not sequences:
            _logger.info("❌ No sequences found for current shift.")
            return False

        # ==============================
        # 🔍 DEBUG: Show available salespersons in current shift
        # ==============================

        current_shift = sequences[0].shift

        _logger.info("===================================================")
        _logger.info("📌 CURRENT SHIFT: %s (ID=%s)",
                     current_shift.shift_name, current_shift.id)
        _logger.info("Shift Time: %.2f -> %.2f",
                     current_shift.from_date, current_shift.to_date)
        _logger.info("Branch: %s (ID=%s)",
                     branch.branch_name, branch.id)
        _logger.info("🕒 Current Hour: %.2f", current_hour)

        _logger.info(" AVAILABLE SALESPERSONS IN THIS SHIFT (ORDERED):")

        for seq in sequences:
            _logger.info(
                "   ➜ SeqID=%s | Order=%s | UserID=%s | Name=%s",
                seq.id,
                seq.sequence,
                seq.sales_person.id,
                seq.sales_person.name,
            )

        _logger.info("===================================================")

        # 5) Round Robin Logic

        current_shift_id = current_shift.id
        param_key = f'last_sequence_id_{branch.id}_{current_shift_id}'
        config = self.env['ir.config_parameter'].sudo()

        last_seq_id_str = config.get_param(param_key)

        try:
            last_seq_id = int(last_seq_id_str) if last_seq_id_str else None
        except (TypeError, ValueError):
            last_seq_id = None

        _logger.info("--------------------------------------------------")
        _logger.info("VALID IDS ORDERED: %s",
                     [(seq.id, seq.sales_person.name) for seq in sequences])
        _logger.info("Stored last_seq_id from param '%s' = %s",
                     param_key, last_seq_id)
        _logger.info("--------------------------------------------------")

        valid_ids = sequences.ids

        if last_seq_id in valid_ids:
            current_index = valid_ids.index(last_seq_id)
            next_index = (current_index + 1) % len(valid_ids)
            next_seq = sequences[next_index]

            _logger.info(
                "last_seq_id %s found at index %s -> Next index %s (seq id=%s)",
                last_seq_id, current_index, next_index, next_seq.id
            )
        else:
            _logger.info("last_seq_id not present in valid_ids")
            next_seq = sequences[0]
            _logger.info("Choosing first valid seq id=%s", next_seq.id)

        # Save new pointer
        config.set_param(param_key, str(next_seq.id))

        _logger.info(
            "✅ Selected salesperson: %s (seq id=%s) -> Saved param key %s",
            next_seq.sales_person.name,
            next_seq.id,
            param_key
        )

        return next_seq.sales_person

    def action_distribute(self):
        """Button action to create a CRM Opportunity and assign next salesperson"""
        self.ensure_one()
        
        # Check if partner already has a salesperson assigned
        if self.partner_id.user_id:
            # Use the existing salesperson from partner
            salesperson = self.partner_id.user_id
            _logger.info("Partner id=%s already has salesperson id=%s. Reusing existing assignment.", 
                        self.partner_id.id, salesperson.id)
        else:
            # Get next salesperson from distribution logic
            salesperson = self._get_next_salesperson()
            
            # Save this salesperson to the partner for future use
            if salesperson:
                self.partner_id.write({'user_id': salesperson.id})
                _logger.info("Assigned new salesperson id=%s to partner id=%s", 
                            salesperson.id, self.partner_id.id)

        partner_name = self.partner_id.name or 'Unknown'
        # ✅ Use actual field names from res.brand and res.sub.brand
        sub_brand_names = self.sub_brand_id2.mapped('sub_brand_name')
        brand_names = self.brand_id2.mapped('brand_name')

        # Name will be auto-generated by crm_lead_sequence module based on branch/year/month
        lead = self.env['crm.lead'].create({
            'sla_duration': '00:00:00',
            'marketing_offer': self.marketing_offer.id,
            'call_type': self.call_type.id,
            'partner_id': self.partner_id.id,
            'branch_name': self.branch_id.id if self.branch_id else False,
            'area_name': self.area_id.id if self.area_id else False,
            'source_name': self.source_id.id,
            'user_id': salesperson.id if salesperson else False,
            'type': 'opportunity',
            'brand_name2': [(6, 0, self.brand_id2.ids)],
            'sub_brand_name2': [(6, 0, self.sub_brand_id2.ids)],
            'brand_used_id': [(6, 0, self.brand_used_id.ids)],
            'sub_brand_used_id': [(6, 0, self.sub_brand_used_id.ids)],
            'model': self.model,
            'opportunity_type': self.opportunity_type,
            'kilometers': self.kilometers,
            'service_id': self.service_id.id if self.service_id else False,
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'Opportunity',
            'view_mode': 'form',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'target': 'current',
        }

        # if self.partner_id:
        #     self.partner_id.is_opportunity = True
        #
        # return {
        #     'type': 'ir.actions.act_window',
        #     'name': 'Opportunity',
        #     'view_mode': 'form',
        #     'res_model': 'crm.lead',
        #     'res_id': lead.id,
        #     'target': 'current',
        # }
