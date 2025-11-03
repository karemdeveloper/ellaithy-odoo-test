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
    brand_id2 = fields.Many2many('res.brand', string="Brand(s)", required=True)
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
    ], string='Opportunity Type', tracking=True)
    sub_brand_id = fields.Many2one('res.sub.brand', string="Sub Brand", required=False)
    sub_brand_id2 = fields.Many2many('res.sub.brand', string="Sub Brand(s)", required=True)
    sub_brand_used_id = fields.Many2many(
        'res.sub.brand',
        'opportunity_wizard_used_sub_brand_rel',
        'wizard_id',
        'sub_brand_id',
        string="Used Sub Brand(s)"
    )
    area_id = fields.Many2one('res.area', string="Area")
    branch_id = fields.Many2one('res.branch', string="Branch")
    source_id = fields.Many2one('res.source', string="Source", required=True)
    sla_duration = fields.Float(string="SLA Duration")
    partner_id = fields.Many2one('res.partner', string="Customer")
    marketing_offer = fields.Many2one('marketing.offers', string='Marketing Offer')
    call_type = fields.Many2one('call.type', string='Call Type')
    model = fields.Char(string="Model")
    kilometers = fields.Char(string="Kilometers")

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

    #################################################################################

    def _get_next_salesperson(self):
        """Determine the next salesperson for the selected branch (Round Robin).
        Added detailed logs to trace time comparison and sequence selection.
        """
        self.ensure_one()
        branch = self.branch_id
        if not branch:
            _logger.info("No branch selected in wizard. Exiting _get_next_salesperson.")
            return False

        # _logger.info("===== _get_next_salesperson START for branch id=%s (%s) =====", branch.id, branch.name)

        # 1) sales teams for branch
        sales_teams = self.env['crm.team'].search([('branch_name', '=', branch.id)])
        if not sales_teams:
            return False

        # 2) active team members
        active_members = self.env['crm.team.member'].search([
            ('crm_team_id', 'in', sales_teams.ids),
            ('state', '=', 'active')
        ])
        _logger.info("Found %d active team member(s) in these teams.", len(active_members))
        if not active_members:
            _logger.info("No active team members for branch %s. Exiting.", branch.name)
            return False

        # Get server UTC time (Odoo always stores in UTC)
        utc_now = fields.Datetime.now()

        # Convert it to Egypt local time (Africa/Cairo)
        egypt_tz = pytz.timezone('Africa/Cairo')
        local_now = utc_now.replace(tzinfo=pytz.utc).astimezone(egypt_tz)

        # Calculate current hour in float
        current_hour = local_now.hour + local_now.minute / 60.0

        _logger.info("UTC now: %s | Egypt local time: %s | current_hour=%.4f",
                     utc_now, local_now, current_hour)
        # 3a) Try to get sequences for branch filtered by active members' users AND where the SHIFT is current
        shift_filtered_domain = [
            ('branch', '=', branch.id),
            ('state', '=', 'active'),
            ('sales_person', 'in', active_members.mapped('user_id').ids),
            ('shift.from_date', '<=', current_hour),
            ('shift.to_date', '>=', current_hour),
        ]
        sequences = self.env['distribute.sequence'].search(shift_filtered_domain, order='sequence asc, id asc')
        _logger.info("After shift filter: found %d sequence(s) matching current shift.", len(sequences))

        # log details of matched sequences (from/to)
        for seq in sequences:
            _logger.info("  -> seq id=%s sales_person=%s from=%.4f to=%.4f",
                         seq.id,
                         getattr(seq.sales_person, 'login', getattr(seq.sales_person, 'name', seq.sales_person.id)),
                         float(seq.from_date) if seq.from_date is not None else None,
                         float(seq.to_date) if seq.to_date is not None else None)

        # 3b) If no sequences match the current shift, fallback to all active sequences for the branch (no shift filter)
        if not sequences:
            fallback_domain = [
                ('branch', '=', branch.id),
                ('state', '=', 'active'),
                ('sales_person', 'in', active_members.mapped('user_id').ids)
            ]
            sequences = self.env['distribute.sequence'].search(fallback_domain, order='sequence asc, id asc')
            _logger.info("Fallback: found %d active sequence(s) for branch (no shift filter).", len(sequences))
            for seq in sequences:
                _logger.info("  -> fallback seq id=%s sales_person=%s from=%.4f to=%.4f",
                             seq.id,
                             getattr(seq.sales_person, 'login', getattr(seq.sales_person, 'name', seq.sales_person.id)),
                             float(seq.from_date) if seq.from_date is not None else None,
                             float(seq.to_date) if seq.to_date is not None else None)

        if not sequences:
            _logger.info("No sequences available after fallback for branch %s. Exiting.", branch.name)
            return False

        # 4) Round Robin using last sequence id
        config = self.env['ir.config_parameter'].sudo()
        param_key = f'last_sequence_id_{branch.id}'
        last_seq_id_str = config.get_param(param_key)  # stored as string or None
        _logger.info("ir.config_parameter '%s' = %s", param_key, last_seq_id_str)

        next_salesperson = False
        try:
            last_seq_id = int(last_seq_id_str) if last_seq_id_str else None
        except (TypeError, ValueError):
            last_seq_id = None
        _logger.info("Interpreted last_seq_id as: %s", last_seq_id)

        valid_ids = sequences.ids
        _logger.info("Valid sequence ids after filtering: %s", valid_ids)

        next_seq = False
        # Safer round robin: if last_seq_id is still in valid_ids, pick the next one.
        # If it's not present (changed conditions), start from the first valid record.
        if last_seq_id in valid_ids:
            current_index = valid_ids.index(last_seq_id)
            next_index = (current_index + 1) % len(valid_ids)
            next_seq = sequences[next_index]
            _logger.info("last_seq_id %s found at index %s -> choosing index %s (seq id=%s)",
                         last_seq_id, current_index, next_index, next_seq.id)
        else:
            next_seq = sequences[0]
            _logger.info("last_seq_id not present in valid_ids -> choosing first valid seq id=%s", next_seq.id)

        # Extra safety: if for any reason next_seq doesn't have a sales_person or is invalid, search forward for first valid
        if not next_seq.sales_person:
            _logger.warning(
                "Chosen sequence id=%s has no sales_person. Searching for next valid sequence with sales_person.",
                getattr(next_seq, 'id', None))
            found = False
            for seq in sequences:
                if seq.sales_person:
                    next_seq = seq
                    found = True
                    _logger.info("Found fallback seq id=%s with sales_person %s", seq.id, seq.sales_person.id)
                    break
            if not found:
                _logger.warning("No valid sequence with sales_person found. Exiting.")
                return False

        # the salesperson is the user referenced on the chosen sequence row
        if next_seq and next_seq.sales_person:
            next_salesperson = next_seq.sales_person
            # save the sequence id we used (so next time we pick the following row)
            config.set_param(param_key, str(next_seq.id))
            _logger.info("Selected salesperson id=%s (user=%s) from sequence id=%s. Saved last_sequence_id=%s",
                         next_salesperson.id,
                         getattr(next_salesperson, 'login', getattr(next_salesperson, 'name', next_salesperson.id)),
                         next_seq.id, next_seq.id)
        else:
            _logger.warning("Next sequence found but it has no sales_person. Returning False.")
            return False

        _logger.info("===== _get_next_salesperson END (selected user id=%s) =====", next_salesperson.id)
        return next_salesperson  ####################################################################################

    def action_distribute(self):
        """Button action to create a CRM Opportunity and assign next salesperson"""
        self.ensure_one()
        salesperson = self._get_next_salesperson()

        partner_name = self.partner_id.name or 'Unknown'
        # ✅ Use actual field names from res.brand and res.sub.brand
        sub_brand_names = self.sub_brand_id2.mapped('sub_brand_name')
        brand_names = self.brand_id2.mapped('brand_name')

        brand_name_str = ', '.join(brand_names) if brand_names else 'NoBrand'
        sub_brand_name_str = ', '.join(sub_brand_names) if sub_brand_names else 'NoSubBrand'

        # count existing leads
        existing_leads_count = self.env['crm.lead'].search_count([
            ('partner_id', '=', self.partner_id.id),
            ('brand_name2', 'in', self.brand_id2.ids),
            ('sub_brand_name2', 'in', self.sub_brand_id2.ids),
        ]) + 1

        seq_number = str(existing_leads_count).zfill(3)
        sequence_str = f"{partner_name}/{brand_name_str}/{sub_brand_name_str}/{seq_number}"

        lead = self.env['crm.lead'].create({
            'name': sequence_str,
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
            # ✅ نقل باقي المعلومات (model + kilometers)
            'model': self.model,
            'kilometers': self.kilometers,
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
