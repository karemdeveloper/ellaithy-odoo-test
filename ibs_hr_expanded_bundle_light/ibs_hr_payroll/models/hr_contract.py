from odoo import api, fields, models

DAYS_IN_MONTH_BASIS = 30.0
DEFAULT_SHIFT_HOURS = 8.0


class HrContract(models.Model):
    _inherit = 'hr.contract'

    # Entered by hand in stock ohrms_overtime; here they follow the wage so a
    # raise moves the overtime rate with it instead of leaving a stale figure.
    over_day = fields.Monetary(
        string='Day Wage', compute='_compute_overtime_wages', store=True,
        readonly=True, help='Wage / 30.')
    over_hour = fields.Monetary(
        string='Hour Wage', compute='_compute_overtime_wages', store=True,
        readonly=True, help='Day wage / hours of the employee shift.')

    def _ibs_shift_hours(self):
        """Daily hours of the employee's shift.

        Average over the days the shift actually works, since a shift can
        give different lengths to different weekdays. Falls back to the
        contract working schedule, then to eight hours.
        """
        self.ensure_one()
        lines = self.employee_id.effective_shift_id.line_ids.filtered(
            lambda line: not line.is_off and line.number_of_hours > 0)
        if lines:
            return sum(lines.mapped('number_of_hours')) / len(lines)
        return self.resource_calendar_id.hours_per_day or DEFAULT_SHIFT_HOURS

    @api.depends('wage', 'employee_id.shift_id.line_ids.number_of_hours',
                 'employee_id.shift_id.line_ids.is_off',
                 'employee_id.company_id.ibs_default_shift_id.line_ids.number_of_hours',
                 'employee_id.company_id.ibs_default_shift_id.line_ids.is_off',
                 'resource_calendar_id.hours_per_day')
    def _compute_overtime_wages(self):
        for contract in self:
            day_wage = contract.wage / DAYS_IN_MONTH_BASIS
            contract.over_day = day_wage
            contract.over_hour = day_wage / contract._ibs_shift_hours()
