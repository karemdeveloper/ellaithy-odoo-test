from odoo import models, fields,api
from odoo.exceptions import UserError
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT
import pytz

class CrmLead(models.Model):
    _inherit = 'crm.lead'
    branch_name = fields.Many2one('res.branch', string="Branch")
    area_name = fields.Many2one('res.area', string="Area")
    brand_name = fields.Many2one('res.brand', string="Brand", required=True)
    source_name = fields.Many2one('res.source', string="Source")
    sales_team = fields.Many2one('crm.team', string="Sales team")
    sub_brand_name = fields.Many2one('res.sub.brand', string="Sub Brand", required=True)
    sla_duration = fields.Char(string="SLA Duration", compute='_compute_sla_duration')
    marketing_offer=fields.Many2one('marketing.offers',string='Marketing offer')
    call_type=fields.Many2one('call.type',string='Call Type')
    feedback_ids = fields.One2many('crm.feedback', 'lead_id', string="Feedback Lines")
###################################################################################
    @api.onchange('area_name')
    def _onchange_area_name(self):
        for rec in self:
            rec.branch_name = rec.area_name.branch_area.id if rec.area_name else False
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
