from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# CR 2.18 -- the group that may raise an advance. Anyone outside it is a
# self-service employee, who must go through HR instead.
HR_GROUP = 'ellithy_ohrms_bridge.advance_generalist'

# CR 2.19 -- the group that may waive the earned-to-date ceiling. Deliberately
# narrower than HR_GROUP: raising a request is daily HR work, signing off on
# breaking a policy ceiling is not. HR Admin implies HR Personnel, so an admin
# can do both.
CEILING_EXCEPTION_GROUP = 'ellithy_ohrms_bridge.advance_admin'

# Egyptian payroll convention, and the same basis the discipline ledger uses:
# a month is thirty days regardless of the calendar.
DAYS_IN_MONTH_BASIS = 30.0


class SalaryAdvance(models.Model):
    """Ellithy's advance policy on the OpenHRMS salary advance.

    * CR 2.18 -- advances are raised by HR, not through self-service.
    * CR 2.19 -- an advance may not exceed what the employee has already
      earned this month, counted from the 1st to the date of the request,
      unless HR Admin grants the exception on the request itself.
    """

    _name = 'salary.advance'
    _inherit = ['salary.advance', 'ellithy.hr.action.notification']

    # The vendor calls this "Exceed than Maximum" and helps it as a
    # percentage of the salary structure, which is neither what it did there
    # (it compared against a full month's wage) nor what it does here. Renamed
    # to say plainly which ceiling it lifts. Tracked, because an exception
    # nobody can trace back to a person is not much of a control.
    exceed_condition = fields.Boolean(
        string='Exception: Allow Above Earned to Date', tracking=True,
        help='CR 2.19 -- lets this request go above the earned-to-date '
             'ceiling, and past the vendor check against the full contract '
             'wage at approval. HR Admin only, and recorded in the chatter.')

    earned_to_date = fields.Monetary(
        string='Earned to Date', compute='_compute_earned_to_date',
        currency_field='currency_id',
        help='CR 2.19 -- pay accrued from the 1st of the month to the date of '
             'the request, or from the contract start when that is later. '
             'The advance may not exceed it.')

    # ------------------------------------------------------------------
    # CR 2.19 -- the earned-to-date ceiling
    # ------------------------------------------------------------------
    def _advance_contract(self):
        """The contract that actually covers the request date.

        ``_ibs_contract_on`` falls back to the employee's latest contract
        when none covers the date. That is right for recomputing an old
        payslip, and wrong here: a contract that ended in June is not a
        salary anyone is still earning against in September, and one that
        starts on the 15th has earned nothing on the 10th. An advance needs
        a live salary source, so the fallback is refused rather than used.
        """
        if len(self) != 1 or not self.date or not self.employee_id:
            return self.env['hr.contract']
        contract = self.employee_id.sudo()._ibs_contract_on(self.date)
        if not contract or contract.date_start > self.date:
            return self.env['hr.contract']
        if contract.date_end and contract.date_end < self.date:
            return self.env['hr.contract']
        return contract

    def _earned_days(self, contract):
        """Days of pay accrued this month, on the thirty-day basis.

        Counted from the 1st, or from the contract start when that falls
        later in the same month: someone hired on the 15th has earned six
        days by the 20th, not twenty. The 31st is worth the same as the
        30th, since the basis is a thirty-day month.
        """
        first = max(self.date.replace(day=1), contract.date_start)
        return max(min(self.date.day, 30) - min(first.day, 30) + 1, 0)

    def _earned_to_date(self):
        """Pay accrued from the 1st of the month to ``date``."""
        contract = self._advance_contract()
        if not contract or not contract.wage:
            return 0.0
        return ((contract.wage / DAYS_IN_MONTH_BASIS)
                * self._earned_days(contract))

    @api.depends('employee_id', 'date')
    def _compute_earned_to_date(self):
        for advance in self:
            advance.earned_to_date = advance._earned_to_date()

    @api.constrains('advance', 'date', 'employee_id', 'exceed_condition')
    def _check_advance_ceiling(self):
        """The ceiling, and the one tick box that lifts it.

        ``exceed_condition`` is listed above so that clearing it re-runs
        this: an exception withdrawn on a request that is still over the
        ceiling has to be refused, not silently left standing.

        The exception waives the missing-salary refusal too, not only the
        comparison -- with no ceiling being applied there is no ceiling to
        fail to compute. The vendor's ``approve_request`` still refuses an
        employee with no contract at all, so that case does not slip
        through to an approval.
        """
        for advance in self:
            if advance.date and advance.date > fields.Date.context_today(advance):
                raise ValidationError(_(
                    'A salary advance cannot be dated in the future. '
                    'Use today or an earlier date so the ceiling reflects earned pay.'))
            if advance.advance < 0:
                raise ValidationError(_('A salary advance must be a positive amount.'))
            if not advance.advance or advance.exceed_condition:
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
                    'Requested %(amount)s. HR Admin can allow it on this '
                    'request with "Exception: Allow Above Earned to Date".',
                    date=advance.date, earned=round(earned, 2),
                    amount=advance.advance))

    def _check_ceiling_exception_granter(self):
        """Who may waive the ceiling, checked on the record.

        Same reasoning as ``_check_hr_author``: hiding the box from the
        form leaves it settable over the ORM, an import or JSON-RPC, and a
        control that only holds in the UI does not hold.
        """
        if self.env.su or self.env.user.has_group(CEILING_EXCEPTION_GROUP):
            return
        raise ValidationError(_(
            'Only HR Admin may allow a salary advance above the '
            'earned-to-date ceiling.'))

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
        self._check_request_employee(vals.get('employee_id', self.env.user.employee_id.id),
                                     'ellithy_ohrms_bridge.advance_generalist')
        if vals.get('exceed_condition'):
            self._check_ceiling_exception_granter()
        return super().create(vals)

    def write(self, vals):
        if 'employee_id' in vals:
            self._check_request_employee(vals['employee_id'], 'ellithy_ohrms_bridge.advance_generalist')
        target = vals.get('state')
        if target in ('cancel', 'reject') and any(record.state == 'approve' for record in self):
            raise ValidationError(_('A released advance must be reversed through accounting and payroll.'))
        if not self.env.su and {'employee_id', 'date', 'advance', 'currency_id'}.intersection(vals) and any(
                record.state in ('waiting_approval', 'approve') for record in self):
            raise ValidationError(_('The terms are locked after HR approval.'))
        if not self.env.su:
            if target == 'approve':
                role, source = 'advance_finance', 'waiting_approval'
            elif target == 'waiting_approval':
                role, source = 'advance_generalist', 'submit'
            elif target in ('submit', 'cancel', 'reject'):
                role, source = 'advance_generalist', None
            elif set(vals).issubset({'journal', 'journal_id', 'debit', 'credit'}):
                role, source = 'advance_finance', None
            else:
                role, source = 'advance_generalist', None
            if not self.env.user.has_group('ellithy_ohrms_bridge.' + role):
                raise ValidationError(_('You are not authorized for this salary advance action.'))
            if source and any(record.state != source for record in self):
                raise ValidationError(_('Follow the salary advance approval order: HR then Finance.'))
            if target in ('waiting_approval', 'approve') and any(
                    record.employee_id.user_id == self.env.user for record in self):
                raise ValidationError(_('You cannot approve your own salary advance.'))
        # Only granting the exception is gated. Withdrawing one makes the
        # request stricter, and the constraint above re-checks it.
        if vals.get('exceed_condition'):
            self._check_ceiling_exception_granter()
        elif 'advance' in vals and 'exceed_condition' not in vals:
            # An exception covers the amount it was granted for, not whatever
            # the amount is raised to afterwards. Without this, HR Personnel
            # could not grant a waiver but could enlarge one, and the ceiling
            # would not stop them: the constraint is standing down.
            for advance in self.filtered('exceed_condition'):
                if advance.currency_id.compare_amounts(
                        vals['advance'], advance.advance) > 0:
                    self._check_ceiling_exception_granter()
                    break
        result = super().write(vals)
        if target == 'submit':
            self._notify_approval_group('ellithy_ohrms_bridge.advance_generalist', _('Salary advance awaiting HR approval'))
        elif target == 'waiting_approval':
            self._notify_approval_group('ellithy_ohrms_bridge.advance_finance', _('Salary advance awaiting Finance approval'))
        elif target in ('approve', 'cancel', 'reject'):
            self._notify_employee(_('Salary advance updated'))
        return result
