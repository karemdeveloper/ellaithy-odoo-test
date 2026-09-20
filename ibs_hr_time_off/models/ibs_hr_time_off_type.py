from odoo import fields, models


class IbsHrTimeOffType(models.Model):
    _name = 'ibs.hr.time.off.type'
    _description = 'Time Off Type'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    approval_route = fields.Selection([
        ('manager', 'HR Generalist (one step)'),
        ('hr', 'HR Generalist (one step)'),
        ('both', 'HR Generalist then HR Admin'),
    ], required=True, default='hr')
    has_attachment = fields.Boolean(string='Has Attachment')
    one_day_per_year = fields.Boolean(string='One Day per Year')
    limit_days = fields.Float(string='Limit (Days)')
    required_period_months = fields.Integer(
        string='Required Period after Joining Date')
    paid = fields.Boolean(default=True)

    code = fields.Selection([
        ('casual', 'Casual'),
        ('annual', 'Annual'),
        ('birthday', 'Birthday'),
        ('public_holiday', 'Public Holiday'),
        ('compensatory_rest', 'Compensatory Rest'),
        ('other', 'Other'),
    ], required=True, default='other', index=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('company_code_unique', 'unique(company_id, code)',
         'Each time off code can appear only once per company.'),
    ]
