from odoo import fields, models


class IbsHrPublicHoliday(models.Model):
    _name = 'ibs.hr.public.holiday'
    _description = 'Public Holiday'
    _order = 'date desc, name'

    name = fields.Char(required=True, translate=True)
    date = fields.Date(required=True, index=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade', index=True)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('company_date_name_unique', 'unique(company_id, date, name)',
         'This public holiday already exists on this date.'),
    ]

