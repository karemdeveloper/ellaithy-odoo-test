from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    shift_id = fields.Many2one(
        'ibs.hr.shift', string='Shift', ondelete='restrict')

