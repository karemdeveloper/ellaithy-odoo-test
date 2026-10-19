from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    shift_id = fields.Many2one(
        'ibs.hr.shift', string='Shift', ondelete='restrict')
    effective_shift_id = fields.Many2one(
        'ibs.hr.shift', string='Working Shift',
        compute='_compute_effective_shift_id',
        help="The employee's own shift, or the company default shift when "
             "none is set.")

    @api.depends('shift_id', 'company_id.ibs_default_shift_id')
    def _compute_effective_shift_id(self):
        for employee in self:
            employee.effective_shift_id = (
                employee.shift_id or employee.company_id.ibs_default_shift_id)
