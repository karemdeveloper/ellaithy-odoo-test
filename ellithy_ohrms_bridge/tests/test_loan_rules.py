from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestLoanRules(EllithyBridgeCommon):
    """CR 2.15 / 2.16 / 2.17 on ``hr.loan``."""

    def _loan(self, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'loan_amount': 3000.0,
            'installment': 3,
            'payment_date': '2026-01-01',
        }
        values.update(kwargs)
        return self.env['hr.loan'].create(values)

    # ---- CR 2.15 -----------------------------------------------------
    def test_a_compliant_request_submits(self):
        loan = self._loan()
        self.assertFalse(loan.eligibility_warning)
        loan.action_submit()
        self.assertEqual(loan.state, 'waiting_approval_1')

    def test_rule_a_less_than_a_year_of_service(self):
        self.employee.joining_date = '2025-09-01'
        loan = self._loan()
        failures = loan._eligibility_failures()
        self.assertEqual(len(failures), 1)
        self.assertIn('Rule A', failures[0])
        with self.assertRaises(ValidationError):
            loan.action_submit()

    def test_rule_b_more_than_twice_the_monthly_salary(self):
        loan = self._loan(loan_amount=6000.01)
        self.assertIn('Rule B', '\n'.join(loan._eligibility_failures()))

    def test_rule_b_exactly_twice_salary_is_allowed(self):
        """The ceiling is inclusive: two times, not less than two times."""
        loan = self._loan(loan_amount=6000.0, installment=6)
        self.assertNotIn('Rule B', '\n'.join(loan._eligibility_failures()))

    def test_rule_c_more_than_ten_instalments(self):
        loan = self._loan(installment=11)
        self.assertIn('Rule C', '\n'.join(loan._eligibility_failures()))

    def test_rule_d_must_settle_inside_the_financial_year(self):
        """A loan starting in October cannot run for six months."""
        loan = self._loan(payment_date='2026-10-01', installment=6)
        self.assertIn('Rule D', '\n'.join(loan._eligibility_failures()))

    def test_rule_d_a_late_start_with_a_short_schedule_passes(self):
        loan = self._loan(payment_date='2026-10-01', installment=3)
        self.assertNotIn('Rule D', '\n'.join(loan._eligibility_failures()))

    # ---- CR 2.16 -----------------------------------------------------
    def test_every_broken_rule_is_reported_not_just_the_first(self):
        self.employee.joining_date = '2026-01-01'
        loan = self._loan(loan_amount=99000.0, installment=24,
                          payment_date='2026-06-01')
        failures = loan._eligibility_failures()
        self.assertEqual(len(failures), 4)
        for rule in ('Rule A', 'Rule B', 'Rule C', 'Rule D'):
            self.assertIn(rule, '\n'.join(failures))

    def test_the_warning_is_visible_while_the_request_is_a_draft(self):
        loan = self._loan(installment=11)
        self.assertIn('Rule C', loan.eligibility_warning)

    def test_the_thresholds_are_parameters(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'ellithy_hr.loan_max_installments', '3')
        loan = self._loan(installment=4)
        self.assertIn('Rule C', '\n'.join(loan._eligibility_failures()))

    # ---- CR 2.17 -----------------------------------------------------
    def test_finance_cannot_approve_before_hr(self):
        loan = self._loan()
        loan.action_submit()
        with self.assertRaises(ValidationError):
            loan.action_double_approve()

    def test_hr_approval_does_not_release_the_loan_on_its_own(self):
        """The vendor would post the journal entry here when the
        ``account.loan_approve`` parameter is unset. CR 2.17 does not allow
        a single signature to do that."""
        loan = self._loan()
        loan.action_submit()
        loan.action_approve()
        self.assertEqual(loan.state, 'waiting_approval_2')
        self.assertTrue(loan.hr_approved_by)
        self.assertTrue(loan.hr_approved_at)
        self.assertFalse(loan.finance_approved_by)
        # HR approval computes the schedule so Finance can see what it signs.
        self.assertTrue(loan.loan_lines)

    def test_hr_cannot_approve_a_draft(self):
        loan = self._loan()
        with self.assertRaises(ValidationError):
            loan.action_approve()

    def test_refusing_requires_a_reason(self):
        loan = self._loan()
        loan.action_submit()
        with self.assertRaises(ValidationError):
            loan.action_refuse()
        loan.refusal_reason = 'Outstanding advance not yet cleared.'
        loan.action_refuse()
        self.assertEqual(loan.state, 'refuse')
