from odoo import models, fields, api

class ResComplaintWizard(models.TransientModel):
    _name = 'res.complaint.wizard'
    _description = 'Complaint Creation Wizard'

    date = fields.Date(string='Date', default=fields.Date.context_today)
    customer_id = fields.Many2one('res.partner', string='Customer', required=True)
    primary_phone = fields.Char(related='customer_id.phone', string='Primary Phone', store=True, readonly=True)
    complaint_reason_id = fields.Many2one('res.complaint.reason', string='Complaint Reason')
    branch_id = fields.Many2one('res.branch', string='Branch')
    department = fields.Many2one('res.department', string='Department')
    escalation_line_id = fields.Many2one('res.escalation', string='Escalation Line')
    solved_by = fields.Selection([
        ('crm', 'CRM'),
        ('ceo', 'CEO'),
        ('credit', 'Credit'),
        ('paper', 'Paper'),
        ('branch_manager', 'Branch Manager'),
        ('accountant', 'Accountant'),
        ('sales_man', 'Sales Man'),
        ('insurance_manager', 'Insurance Manager'),
        ('insurance_specialist', 'Insurance Specialist'),
        ('purchasing', 'Purchasing'),
        ('used', 'Used'),
        ('hr', 'HR'),
        ('team_leader', 'Team Leader'),
        ('inventory', 'Inventory'),
        ('ellaithy_prime_manager', 'Ellaithy Prime Manager'),
        ('it', 'IT'),
    ], string='Solved By')
    validity = fields.Selection([
        ('valid', 'Valid'),
        ('not_valid', 'Not Valid')
    ], string='Valid or Not Valid')
    solving_date = fields.Date(string='Solving Date')
    complaint_duration = fields.Text(string='Complaint Duration')
    complaint_type_id = fields.Many2one('res.complaint.type', string='Complaint Type')

    @api.model
    def default_get(self, fields_list):
        """ Pre-fill customer when opened from partner """
        res = super().default_get(fields_list)
        if self.env.context.get('active_model') == 'res.partner':
            res['customer_id'] = self.env.context.get('active_id')
        return res

    def action_confirm(self):
        """ Create complaint record """
        self.ensure_one()
        self.env['res.complaint'].create({
            'date': self.date,
            'customer_id': self.customer_id.id,
            'complaint_reason_id': self.complaint_reason_id.id,
            'branch_id': self.branch_id.id,
            'department': self.department.id,  # optional mapping
            'escalation_line_id': self.escalation_line_id.id,
            'solved_by': self.solved_by,
            'validity': self.validity,
            'solving_date': self.solving_date,
            'complaint_duration': self.complaint_duration,
            'complaint_type_id': self.complaint_type_id.id,
        })
        return {'type': 'ir.actions.act_window_close'}
