from odoo import models, fields,api

class ResComplaint(models.Model):
    _name = 'res.complaint'
    _description = 'Complaint'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    date = fields.Date(string='Date', tracking=True)
    customer_id = fields.Many2one('res.partner', string='Customer', tracking=True)
    primary_phone = fields.Char(related='customer_id.phone', string='Primary Phone', store=True, readonly=True)
    complaint_reason_id = fields.Many2one('res.complaint.reason', string='Complaint Reason', tracking=True)
    branch_id = fields.Many2one('res.branch', string='Branch', tracking=True)
    department = fields.Many2one('res.department', string='Department', tracking=True)
    escalation_line_id = fields.Many2one('res.escalation', string='Escalation Line', tracking=True)
    solved_by = fields.Selection([('crm', 'CRM'),('ceo', 'CEO'),('credit', 'Credit'),('paper', 'Paper'),('branch_manager', 'Branch Manager'),('accountant', 'Accountant'),('sales_man', 'Sales Man'),('insurance_manager', 'Insurance Manager'),('insurance_specialist', 'Insurance Specialist'),('purchasing', 'Purchasing'),('used', 'Used'),('hr', 'HR'),('team_leader', 'Team Leader'),('inventory', 'Inventory'),('ellaithy_prime_manager', 'Ellaithy Prime Manager'),('it', 'IT'),], string='Solved By', tracking=True)
    validity = fields.Selection([('valid', 'Valid'),('not_valid', 'Not Valid')], string='Valid or Not Valid', tracking=True)
    solving_date = fields.Date(string='Solving Date', tracking=True)
    complaint_duration = fields.Text(string='Complaint Duration', tracking=True)
    complaint_type_id = fields.Many2one('res.complaint.type', string='Complaint Type', tracking=True)