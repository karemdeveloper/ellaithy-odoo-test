from odoo import models, fields, api
from datetime import date

class ResComplaint(models.Model):
    _name = 'res.complaint'
    _description = 'Complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    date = fields.Date(string='Date', tracking=True, default=fields.Date.context_today)
    customer_id = fields.Many2one('res.partner', string='Customer', tracking=True, required=True)
    primary_phone = fields.Char(related='customer_id.phone', string='Primary Phone', store=True, readonly=True)
    complaint_reason_id = fields.Many2one('res.complaint.reason', string='Complaint Reason', 
                                          tracking=True, required=True)
    branch_id = fields.Many2one('res.branch', string='Branch', tracking=True)
    department = fields.Many2one('res.department', string='Department', tracking=True, required=True)
    escalation_line_id = fields.Many2one('res.escalation', string='Escalation Line', tracking=True)
    
    # Salesperson from customer
    salesperson_id = fields.Many2one(related='customer_id.user_id', string='Salesperson', 
                                     store=True, readonly=True, tracking=True)
    
    # Assigned to (Many2many)
    assigned_to_ids = fields.Many2many('res.users', string='Assigned To', tracking=True, required=True)
    
    # Remove validity field (valid/not valid)
    # Remove solved_by field
    
    solving_date = fields.Date(string='Solving Date', tracking=True)
    complaint_duration = fields.Integer(string='Complaint Duration (Days)', compute='_compute_complaint_duration', 
                                        store=True, tracking=True)
    complaint_type_id = fields.Many2one('res.complaint.type', string='Type of Complaint', 
                                        tracking=True, required=True)
    
    # SLA Duration from complaint type
    sla_duration = fields.Char(related='complaint_type_id.sla_duration', string='SLA Duration', 
                               store=True, readonly=True)
    
    # Difference between SLA duration and Complaint duration
    sla_difference = fields.Char(string='Difference (Complaint - SLA)', 
                                 compute='_compute_sla_difference', store=True)
    
    # Difference between created on and today
    days_since_creation = fields.Integer(string='Days Since Creation', 
                                         compute='_compute_days_since_creation', store=True)
    
    complaint_state = fields.Selection([
        ('new', 'New'),
        ('under_investigate', 'Under Investigate'),
        ('solved', 'Solved'),
    ], string='Complaint State', tracking=True, default='new')

    @api.depends('date', 'solving_date')
    def _compute_complaint_duration(self):
        """Calculate complaint duration in days"""
        for record in self:
            if record.date and record.solving_date:
                start_date = fields.Date.from_string(str(record.date))
                end_date = fields.Date.from_string(str(record.solving_date))
                record.complaint_duration = (end_date - start_date).days
            else:
                record.complaint_duration = 0
    
    @api.depends('complaint_duration', 'sla_duration')
    def _compute_sla_difference(self):
        """Calculate difference between complaint duration and SLA duration"""
        for record in self:
            if record.sla_duration and record.complaint_duration:
                try:
                    # Try to parse SLA duration as integer (days)
                    sla_days = int(record.sla_duration)
                    difference = record.complaint_duration - sla_days
                    record.sla_difference = f"{difference} days"
                except ValueError:
                    # If SLA is not a number, just show the text
                    record.sla_difference = f"{record.complaint_duration} days (SLA: {record.sla_duration})"
            else:
                record.sla_difference = "N/A"
    
    @api.depends('create_date')
    def _compute_days_since_creation(self):
        """Calculate days between creation date and today"""
        for record in self:
            if record.create_date:
                created_date = fields.Date.from_string(str(record.create_date.date()))
                today = fields.Date.context_today(record)
                record.days_since_creation = (today - created_date).days
            else:
                record.days_since_creation = 0

    def action_under_investigate(self):
        for record in self:
            record.complaint_state = 'under_investigate'
            record.message_post(body="Complaint moved to <b>Under Investigation</b> stage.")
        return True

    def action_mark_solved(self):
        for record in self:
            record.complaint_state = 'solved'
            record.solving_date = fields.Date.context_today(self)
            record.message_post(
                body=f"Complaint marked as <b>Solved</b>. Duration: {record.complaint_duration} days.")
        return True