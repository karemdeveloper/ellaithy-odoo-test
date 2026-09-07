from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# CR 2.17 -- a loan is approved by HR first and by Finance second.
#
# ``ohrms_loan_accounting`` already carries a two-signature chain --
# draft -> waiting_approval_1 -> waiting_approval_2 -> approve -- so there is
# no new state to invent. What it does NOT do is make that chain mandatory:
# the second signature only happens when the ``account.loan_approve``
# parameter is set, and otherwise ``action_approve`` posts the journal entry
# on the spot. CR 2.17 is not conditional, so the HR step is implemented here
# rather than delegated to a setting that can be switched off.
HR_APPROVED = 'waiting_approval_2'


class HrLoan(models.Model):
    """Ellithy's loan policy on the OpenHRMS loan request.

    Two changes, both from the requirements session:

    * CR 2.15/2.16 -- four eligibility rules, checked on submission, with a
      message that names every rule the request breaks rather than the first.
    * CR 2.17 -- an HR approval and then a Finance approval, each recorded
      against the user who gave it.
    """

    _inherit = 'hr.loan'

    hr_approved_by = fields.Many2one(
        'res.users', string='HR Approved By', readonly=True, copy=False)
    hr_approved_at = fields.Datetime(
        string='HR Approved On', readonly=True, copy=False)
    finance_approved_by = fields.Many2one(
        'res.users', string='Finance Approved By', readonly=True, copy=False)
    finance_approved_at = fields.Datetime(
        string='Finance Approved On', readonly=True, copy=False)
    refusal_reason = fields.Text(
        string='Refusal Reason', copy=False,
        help='Required to refuse a request.')
    eligibility_warning = fields.Text(
        string='Eligibility', compute='_compute_eligibility_warning',
        help='CR 2.16 -- the rules this request currently breaks, shown while '
             'it is still editable.')

    # ------------------------------------------------------------------
    # CR 2.15 / 2.16 -- eligibility
    # ------------------------------------------------------------------
    @api.model
    def _loan_rule_params(self):
        """Eligibility thresholds, as parameters rather than constants.

        These are policy figures confirmed in the requirements session, so HR
        changes them from Settings without a code release.
        """
        get = self.env['ir.config_parameter'].sudo().get_param

        def number(key, default):
            try:
                return float(get(key, default))
            except (TypeError, ValueError):
                return float(default)

        return {
            'min_service_months': number(
                'ellithy_hr.loan_min_service_months', 12),
            'max_salary_multiple': number(
                'ellithy_hr.loan_max_salary_multiple', 2),
            'max_installments': int(number(
                'ellithy_hr.loan_max_installments', 10)),
        }

    def _fiscal_year_end(self, on_date):
        """Last day of the financial year containing ``on_date``.

        Reads the company's fiscal year end when Accounting is installed and
        falls back to 31 December, which is the Egyptian statutory default.
        """
        company = self.employee_id.company_id or self.env.company
        day = int(getattr(company, 'fiscalyear_last_day', 31) or 31)
        month = int(getattr(company, 'fiscalyear_last_month', 12) or 12)
        end = fields.Date.to_date(f'{on_date.year}-{month:02d}-{day:02d}')
        if end < on_date:
            end = fields.Date.to_date(
                f'{on_date.year + 1}-{month:02d}-{day:02d}')
        return end

    def _eligibility_failures(self):
        """Every rule this request breaks, worded for the requester.

        CR 2.16 asks for a message naming the rule that was violated, so the
        checks are collected rather than short-circuited: an employee who
        breaks three rules should be told all three, not made to resubmit
        three times.
        """
        self.ensure_one()
        params = self._loan_rule_params()
        employee = self.employee_id
        start = self.payment_date or self.date or fields.Date.context_today(
            self)
        failures = []

        # (a) at least a year of service
        joined = employee.joining_date
        months_required = int(params['min_service_months'])
        if not joined:
            failures.append(_(
                'Rule A (service): %(name)s has no joining date on file, so '
                'length of service cannot be verified.', name=employee.name))
        else:
            eligible_from = joined + relativedelta(months=months_required)
            if start < eligible_from:
                failures.append(_(
                    'Rule A (service): a loan requires %(months)s months of '
                    'service. %(name)s joined on %(joined)s and becomes '
                    'eligible on %(eligible)s.',
                    months=months_required, name=employee.name,
                    joined=joined, eligible=eligible_from))

        # (b) at most twice the monthly salary
        contract = employee.sudo()._ibs_contract_on(start)
        wage = contract.wage if contract else 0.0
        if not wage:
            failures.append(_(
                'Rule B (amount): no contract salary is on file for %(name)s '
                'on %(date)s, so the ceiling cannot be applied.',
                name=employee.name, date=start))
        else:
            ceiling = wage * params['max_salary_multiple']
            if self.loan_amount > ceiling:
                failures.append(_(
                    'Rule B (amount): a loan may not exceed %(multiple)s x '
                    'monthly salary (%(ceiling)s). Requested %(amount)s.',
                    multiple=int(params['max_salary_multiple']),
                    ceiling=ceiling, amount=self.loan_amount))

        # (c) at most ten instalments
        if self.installment > params['max_installments']:
            failures.append(_(
                'Rule C (instalments): a loan may run for at most %(max)s '
                'instalments. Requested %(count)s.',
                max=params['max_installments'], count=self.installment))

        # (d) settled inside the financial year, whatever month it starts
        final_due = start + relativedelta(months=max(self.installment - 1, 0))
        year_end = self._fiscal_year_end(start)
        if final_due > year_end:
            failures.append(_(
                'Rule D (financial year): the loan must be fully repaid by '
                '%(year_end)s. This schedule runs to %(final)s.',
                year_end=year_end, final=final_due))

        return failures

    @api.depends('employee_id', 'loan_amount', 'installment', 'payment_date',
                 'state')
    def _compute_eligibility_warning(self):
        """Show the rules a draft breaks before the requester submits it."""
        for loan in self:
            if loan.state != 'draft' or not loan.employee_id:
                loan.eligibility_warning = False
                continue
            failures = loan._eligibility_failures()
            loan.eligibility_warning = (
                '\n'.join('- %s' % failure for failure in failures)
                if failures else False)

    def action_check_eligibility(self):
        """Raise CR 2.16's message, or pass silently."""
        for loan in self:
            failures = loan._eligibility_failures()
            if failures:
                raise ValidationError(
                    _('This loan request cannot be submitted:') +
                    '\n\n- ' + '\n- '.join(failures))

    # ------------------------------------------------------------------
    # CR 2.17 -- approval cycle: employee -> HR -> Finance
    # ------------------------------------------------------------------
    def action_submit(self):
        """Gate submission on eligibility."""
        self.action_check_eligibility()
        return super().action_submit()

    def action_approve(self):
        """HR's signature -- the first of the two.

        Deliberately does not delegate to the vendor method. That method
        branches on ``account.loan_approve``: with the parameter unset it
        posts the loan's journal entry and jumps straight to Approved, which
        is the single-signature behaviour CR 2.17 replaces. Writing the HR
        step directly makes the second signature unconditional.
        """
        for loan in self:
            if loan.state != 'waiting_approval_1':
                raise ValidationError(
                    _('Only a submitted request awaits HR approval.'))
            if not loan.loan_lines:
                loan.action_compute_installment()
            loan.write({
                'state': HR_APPROVED,
                'hr_approved_by': self.env.user.id,
                'hr_approved_at': fields.Datetime.now(),
            })
        return True

    def action_double_approve(self):
        """Finance's signature, which releases the money.

        The vendor method posts the journal entry and moves the request to
        Approved; all this adds is the gate and the record of who signed.
        """
        for loan in self:
            if loan.state != HR_APPROVED:
                raise ValidationError(_(
                    'Finance approves only after HR has approved. Ask HR to '
                    'review this request first.'))
        result = super().action_double_approve()
        self.write({
            'finance_approved_by': self.env.user.id,
            'finance_approved_at': fields.Datetime.now(),
        })
        return result

    def action_refuse(self):
        """CR 2.14's principle applied to loans: refusal carries a reason."""
        for loan in self:
            if not loan.refusal_reason:
                raise ValidationError(
                    _('Refusing a request requires a reason.'))
        return super().action_refuse()

    def action_reset_to_draft(self):
        """Send a refused or cancelled request back for correction."""
        return self.write({
            'state': 'draft',
            'hr_approved_by': False, 'hr_approved_at': False,
            'finance_approved_by': False, 'finance_approved_at': False,
        })
