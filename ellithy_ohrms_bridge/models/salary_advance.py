from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# CR 2.18 -- the group that may raise an advance. Anyone outside it is a
# self-service employee, who must go through HR instead.
HR_GROUP = 'ellithy_hr_base.group_ellithy_hr_personnel'

# Egyptian payroll convention, and the same basis the discipline ledger uses:
# a month is thirty days regardless of the calendar.
DAYS_IN_MONTH_BASIS = 30.0


class SalaryAdvance(models.Model):
    """Ellithy's advance policy on the OpenHRMS salary advance.

    * CR 2.18 -- advances are raised by HR, not through self-service.
    * CR 2.19 -- an advance may not exceed what the employee has already
      earned this month, counted from the 1st to the date of the request.
    """

    _inherit = 'salary.advance'

    earned_to_date = fields.Monetary(
        string='Earned to Date', compute='_compute_earned_to_date',
        currency_field='currency_id',
        help='CR 2.19 -- pay accrued from the 1st of the month to the date of '
             'the request. The advance may not exceed it.')

    # ------------------------------------------------------------------
    # CR 2.19 -- the earned-to-date ceiling
    # ------------------------------------------------------------------
    def _earned_to_date(self):
        """Pay accrued from the 1st of the month to ``date``."""
        if len(self) != 1 or not self.date or not self.employee_id:
            return 0.0
        contract = self.employee_id.sudo()._ibs_contract_on(self.date)
        if not contract or not contract.wage:
            return 0.0
        return (contract.wage / DAYS_IN_MONTH_BASIS) * self.date.day

    @api.depends('employee_id', 'date')
    def _compute_earned_to_date(self):
        for advance in self:
            advance.earned_to_date = advance._earned_to_date()

    @api.constrains('advance', 'date', 'employee_id')
    def _check_advance_ceiling(self):
        for advance in self:
            if not advance.advance:
                continue
            earned = advance._earned_to_date()
            if not earned:
                raise ValidationError(_(
                    'No contract salary is on file for %(name)s on %(date)s, '
                    'so the earned-to-date ceiling cannot be applied.',
                    name=advance.employee_id.name, date=advance.date))
            if advance.currency_id.compare_amounts(
                    advance.advance, earned) > 0:
                raise ValidationError(_(
                    'A salary advance may not exceed the amount earned from '
                    'the 1st of the month to %(date)s, which is %(earned)s. '
                    'Requested %(amount)s.',
                    date=advance.date, earned=round(earned, 2),
                    amount=advance.advance))

    # ------------------------------------------------------------------
    # CR 2.18 -- HR raises the request, not the employee
    # ------------------------------------------------------------------
    def _check_hr_author(self):
        """Enforced on the record, not only hidden in the UI.

        The menu can be hidden from self-service, but the model is still
        reachable through the ORM, an imported file or a shared URL, so the
        rule has to live where it cannot be walked around.
        """
        if self.env.su or self.env.user.has_group(HR_GROUP):
            return
        raise ValidationError(_(
            'Salary advance requests are created by the HR department only. '
            'Please contact HR to raise this request.'))

    @api.model
    def create(self, vals):
        self._check_hr_author()
        return super().create(vals)
