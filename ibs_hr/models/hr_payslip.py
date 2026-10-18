from odoo import _, api, fields, models

# Code of the salary rule that carries the disciplinary deduction. It is
# declared in ``data/hr_salary_rule_data.xml`` together with its rule input.
PENALTY_INPUT_CODE = 'PENALTY'

# The legacy platform expressed penalties in DAYS and resolved them at
# basic / 30, regardless of the length of the month. Reproduced deliberately:
# changing the divisor would silently restate 9,976 historical payslips.
DAYS_IN_MONTH_BASIS = 30.0


class HrPayslip(models.Model):
    """Disciplinary penalties on the standard payslip.

    CR 2.12 caps disciplinary deductions at five days of pay per month and
    carries the remainder into following months. That makes a penalty a
    balance to be drawn down rather than a one-off charge, so the payslip
    cannot simply sum the penalties dated inside its period:

      * it must consider arrears from earlier months, which is the whole
        point of a ceiling;
      * it must take penalties by execution date (CR 2.11), not by the date
        of the violation, so a penalty raised late still lands in the month
        management intends;
      * and it must record how much of each penalty it actually took, which
        is what ``ibs.hr.warning.deduction`` is for.

    The plan is computed on demand, so recomputing a draft payslip has no
    side effects, and is written to the ledger only when the payslip is
    confirmed. Resetting to draft releases the ledger rows, which returns
    those days to the employee's outstanding balance.
    """

    _inherit = 'hr.payslip'

    penalty_deduction_ids = fields.One2many(
        'ibs.hr.warning.deduction', 'payslip_id', string='Penalty Deductions',
        readonly=True)
    penalty_days_taken = fields.Float(
        string='Penalty Days Taken', digits=(6, 2),
        compute='_compute_penalty_days',
        help='Days of pay deducted for discipline on this payslip, after the '
             'monthly ceiling.')
    penalty_days_deferred = fields.Float(
        string='Penalty Days Deferred', digits=(6, 2),
        compute='_compute_penalty_days',
        help='Days that exceeded the monthly ceiling and roll into a later '
             'payslip.')
    penalty_amount = fields.Float(
        string='Penalty Amount', compute='_compute_penalty_days')

    # ------------------------------------------------------------------
    # Upstream defect, fixed here rather than in the vendor module
    # ------------------------------------------------------------------
    # ``hr_payroll_community`` declares this compute with no ``@api.depends``,
    # so once the field has been read it never refreshes. That matters because
    # ``hr_payroll_account_community.action_payslip_done`` reads it AFTER
    # calling ``action_compute_sheet()``: it sees the pre-compute value, finds
    # no lines, and aborts the confirmation with "you have to choose Debit and
    # Credit account for at least one salary rule" -- an error about accounts
    # that has nothing to do with accounts.
    #
    # Every payslip confirmation fails this way, which also blocks the CR 2.12
    # ledger below, since that is booked on confirmation. Redeclaring the
    # dependency is the whole fix; the compute itself is unchanged.
    details_by_salary_rule_category_ids = fields.One2many(
        compute='_compute_details_by_salary_rule_category_ids')

    @api.depends('line_ids', 'line_ids.category_id')
    def _compute_details_by_salary_rule_category_ids(self):
        return super()._compute_details_by_salary_rule_category_ids()

    # ------------------------------------------------------------------
    # CR 2.12 -- the ceiling and its carry-over
    # ------------------------------------------------------------------
    def _ibs_daily_rate(self):
        """Daily rate for a disciplinary deduction: basic / 30."""
        # A blank or multi payslip is a legitimate input here: the payroll
        # onchange helpers call through on an empty recordset before the
        # user has chosen an employee.
        if len(self) != 1:
            return 0.0
        contract = self.contract_id or self.employee_id.sudo()._ibs_contract_on(
            self.date_to or self.date_from)
        return contract.wage / DAYS_IN_MONTH_BASIS if contract else 0.0

    def _ibs_outstanding_penalties(self):
        """Approved penalties still owed as at the end of this period.

        Oldest execution date first, so a penalty carried over from an
        earlier month is cleared before a newly raised one starts.
        """
        empty = self.env['ibs.hr.warning']
        if len(self) != 1 or not self.employee_id or not self.date_to:
            return empty
        return empty.search([
            ('employee_id', '=', self.employee_id.id),
            ('status', '=', 'approved'),
            ('execution_date', '<=', self.date_to),
            ('is_settled', '=', False),
        ], order='execution_date asc, id asc')

    def _ibs_penalty_plan(self):
        """How this payslip proposes to spend the monthly penalty budget.

        Returns ``(lines, taken_days, deferred_days)``, each line being a
        ``(warning, days, amount)`` triple. Nothing is written -- booking is
        ``_ibs_apply_penalty_plan``'s job.

        A payslip that has already booked its deductions has no plan left to
        make: its budget is spent, and the outstanding balances it can see
        belong to a later month.
        """
        if len(self) != 1 or self.penalty_deduction_ids:
            return [], 0.0, 0.0
        rate = self._ibs_daily_rate()
        ledger = self.env['ibs.hr.warning.deduction'].sudo()
        already_taken = ledger.search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', fields.Date.start_of(self.date_to, 'month')),
            ('date', '<=', fields.Date.end_of(self.date_to, 'month')),
        ]) if self.employee_id and self.date_to else ledger
        budget = max(0.0, ledger.monthly_cap_days() - sum(already_taken.mapped('days')))
        lines, taken, deferred = [], 0.0, 0.0
        for warning in self._ibs_outstanding_penalties():
            outstanding = warning.days_remaining
            if outstanding <= 0:
                continue
            take = min(outstanding, budget) if budget > 0 else 0.0
            if take > 0:
                lines.append((warning, take, take * warning._ibs_day_value(rate)))
                budget -= take
                taken += take
            deferred += outstanding - take
        return lines, taken, deferred

    def _ibs_apply_penalty_plan(self):
        """Book the plan into the ledger. Called once the payslip is done."""
        deduction = self.env['ibs.hr.warning.deduction']
        for payslip in self:
            lines, _taken, _deferred = payslip._ibs_penalty_plan()
            if not lines:
                continue
            deduction.create([{
                'warning_id': warning.id,
                'payslip_id': payslip.id,
                'days': days,
                'amount': amount,
            } for warning, days, amount in lines])
            # Only a penalty taken in full points back at the payslip; a
            # part-paid one stays open so next month picks up its balance.
            payslip.penalty_deduction_ids.warning_id.filtered(
                'is_settled').write({'payslip_id': payslip.id})

    def _ibs_release_penalty_plan(self):
        """Undo the booking, returning the days to the outstanding balance."""
        for payslip in self:
            payslip.penalty_deduction_ids.warning_id.filtered(
                lambda w: w.payslip_id == payslip).write({'payslip_id': False})
            payslip.penalty_deduction_ids.unlink()

    @api.depends('penalty_deduction_ids.days', 'employee_id', 'date_to',
                 'contract_id')
    def _compute_penalty_days(self):
        for payslip in self:
            if payslip.penalty_deduction_ids:
                # Booked: report what was taken, and what the ceiling pushed
                # into later months.
                taken = sum(payslip.penalty_deduction_ids.mapped('days'))
                deferred = sum(payslip._ibs_outstanding_penalties().mapped(
                    'days_remaining'))
                amount = sum(payslip.penalty_deduction_ids.mapped('amount'))
            else:
                lines, taken, deferred = payslip._ibs_penalty_plan()
                amount = sum(line[2] for line in lines)
            payslip.penalty_days_taken = taken
            payslip.penalty_days_deferred = deferred
            payslip.penalty_amount = amount

    # ------------------------------------------------------------------
    # Payroll hooks
    # ------------------------------------------------------------------
    def get_inputs(self, contracts, date_from, date_to):
        """Feed the capped penalty amount into the PENALTY salary rule."""
        result = super().get_inputs(contracts, date_from, date_to)
        # Summed per penalty rather than days x rate, so an amount HR Admin
        # set on a penalty reaches the PENALTY rule as stated.
        lines, _taken, _deferred = self._ibs_penalty_plan()
        amount = sum(line[2] for line in lines)
        for line in result:
            if line.get('code') == PENALTY_INPUT_CODE:
                line['amount'] = amount
        return result

    def action_payslip_done(self):
        self._ibs_lock_payroll_employees()
        result = True
        # Book each slip before computing another slip's remaining budget.
        for payslip in self:
            result = super(HrPayslip, payslip).action_payslip_done()
            payslip._ibs_apply_penalty_plan()
        return result

    def _ibs_lock_payroll_employees(self):
        self.check_access('write')
        self.env.flush_all()
        for employee in self.employee_id.sorted('id'):
            # A row version change makes concurrent REPEATABLE READ payroll
            # transactions retry, so they cannot book from an old snapshot.
            # No employee value changes; this is only a serialization lock.
            self.env.cr.execute('UPDATE hr_employee SET id = id WHERE id = %s', [employee.id])

    def action_payslip_draft(self):
        self._ibs_lock_payroll_employees()
        self._ibs_release_penalty_plan()
        return super().action_payslip_draft()

    def action_payslip_cancel(self):
        self._ibs_lock_payroll_employees()
        self._ibs_release_penalty_plan()
        return super().action_payslip_cancel()

    def action_view_penalty_deductions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Penalty Deductions'),
            'res_model': 'ibs.hr.warning.deduction',
            'view_mode': 'list,form',
            'domain': [('payslip_id', '=', self.id)],
        }
