from odoo import models, fields,api
from odoo.exceptions import UserError
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import pytz
import math


class CrmLead(models.Model):
    _inherit = 'crm.lead'
    branch_name = fields.Many2one('res.branch', string="Branch")
    area_name = fields.Many2one('res.area', string="Area")
    brand_name = fields.Many2one('res.brand', string="Brand", required=False)
    brand_name2 = fields.Many2many('res.brand', string="Brand(s)",required=False)

    source_name = fields.Many2one('res.source', string="Source")
    sales_team = fields.Many2one('crm.team', string="Sales team")
    sub_brand_name = fields.Many2one('res.sub.brand', string="Sub Brand", )
    sub_brand_name2 = fields.Many2many('res.sub.brand', string="Sub Brand(s)", required=False)

    sla_duration = fields.Char(string="SLA Duration", compute='_compute_sla_duration')
    marketing_offer=fields.Many2one('marketing.offers',string='Marketing offer')
    call_type=fields.Many2one('call.type',string='Call Type')
    feedback_ids = fields.One2many('crm.feedback', 'lead_id', string="Feedback Lines")
    has_feedback = fields.Boolean(string="Has Feedback", default=False)
    sub_brand_used_id = fields.Many2many(
        'res.sub.brand',
        'opportunity_used_sub_brand_rel',
        'wizard_id',
        'sub_brand_id',
        string="Used Sub Brand(s)"
    )
    brand_used_id = fields.Many2many(
        'res.brand',
        'opportunity_used_brand_rel',
        'wizard_id',
        'brand_id',
        string="Used Brand(s)")
    model = fields.Char(string="Model")
    kilometers = fields.Char(string="Kilometers")
    opportunity_type = fields.Selection([
        ('new', 'New'),
        ('trade_in', 'Trade In'),
        ('used', 'Used'),
        ('service', 'Service'),
    ], string='Opportunity Type', tracking=True)
    
    opportunity_type_display = fields.Char(
        string='Type',
        compute='_compute_opportunity_type_display',
        store=False
    )
    
    @api.depends('opportunity_type')
    def _compute_opportunity_type_display(self):
        """Display opportunity type as short code"""
        type_map = {
            'new': 'N',
            'used': 'U',
            'trade_in': 'T',
            'service': 'S',
        }
        for rec in self:
            rec.opportunity_type_display = type_map.get(rec.opportunity_type, '')

    ###################################################################################
    @api.onchange('area_name')
    def _onchange_area_name(self):
        for rec in self:
            rec.branch_name = rec.area_name.branch_area.id if rec.area_name else False

    @api.onchange('brand_name2')
    def _onchange_brand_name2(self):
        """Clear sub-brands when brands change (New section)"""
        for rec in self:
            if rec.brand_name2:
                # Keep only sub-brands that belong to selected brands
                valid_sub_brands = rec.sub_brand_name2.filtered(lambda sb: sb.brand in rec.brand_name2)
                rec.sub_brand_name2 = valid_sub_brands
            else:
                # If no brands selected, clear all sub-brands
                rec.sub_brand_name2 = False

    @api.onchange('brand_used_id')
    def _onchange_brand_used_id(self):
        """Clear sub-brands when brands change (Used section)"""
        for rec in self:
            if rec.brand_used_id:
                # Keep only sub-brands that belong to selected brands
                valid_sub_brands = rec.sub_brand_used_id.filtered(lambda sb: sb.brand in rec.brand_used_id)
                rec.sub_brand_used_id = valid_sub_brands
            else:
                # If no brands selected, clear all sub-brands
                rec.sub_brand_used_id = False
########################################################################################
    def _format_timedelta(self, seconds):
        # Format seconds -> HH:MM:SS
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    @api.depends('create_date', 'feedback_ids.date')
    def _compute_sla_duration(self):
        for rec in self:
            if not rec.create_date:
                rec.sla_duration = "00:00:00"
                continue

            # find first feedback date if any
            feedback_date = False
            if rec.feedback_ids:
                # take the earliest feedback record date
                fb = rec.feedback_ids.sorted('date')[0]
                feedback_date = fb.date

            # compute end time: feedback_date if exists else now (server time)
            if feedback_date:
                try:
                    start_dt = fields.Datetime.from_string(rec.create_date)
                    end_dt = fields.Datetime.from_string(feedback_date)
                    delta = (end_dt - start_dt).total_seconds()
                except Exception:
                    delta = 0
            else:
                # if no feedback yet, compute relative to now (server)
                try:
                    start_dt = fields.Datetime.from_string(rec.create_date)
                    now_dt = fields.Datetime.now()
                    delta = (now_dt - start_dt).total_seconds()
                except Exception:
                    delta = 0

            if delta < 0:
                delta = 0
            rec.sla_duration = self._format_timedelta(delta)
##########################################################################################
    def action_open_feedback_wizard(self):
        """Open the wizard for selected leads"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.feedback.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_ids': [(6, 0, self.ids)],
            }
        }

################################################################################################
    late_days = fields.Integer(string="Late Days", compute='_compute_late_days', store=True)

    @api.depends('sla_duration')
    def _compute_late_days(self):
        """Compute late_days as floor(total_hours / 9).
        sla_duration is expected to be 'HH:MM:SS' (string).
        """
        for rec in self:
            rec.late_days = 0
            sd = rec.sla_duration or ''
            # handle cases: empty, already in HH:MM:SS, or unexpected format
            try:
                parts = sd.split(':')
                if len(parts) == 3:
                    hh = float(parts[0])
                    mm = float(parts[1])
                    ss = float(parts[2])
                    total_hours = hh + (mm / 60.0) + (ss / 3600.0)
                elif len(parts) == 2:
                    # sometimes could be "HH:MM"
                    hh = float(parts[0])
                    mm = float(parts[1])
                    total_hours = hh + (mm / 60.0)
                elif sd.strip() != '':
                    # try to parse as float number of hours (e.g., "2.7")
                    total_hours = float(sd)
                else:
                    total_hours = 0.0

                # divide by 9 and take integer part (floor)
                rec.late_days = int(math.floor(total_hours / 9.0))
            except Exception:
                # on any parse error, fallback to 0
                rec.late_days = 0
################################################################################
