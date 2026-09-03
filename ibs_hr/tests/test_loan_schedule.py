from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestLoanSchedule(IbsHrCommon):

    def _loan(self, amount=1000.0, months=4, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'amount': amount,
            'months': months,
            'date': '2026-05-15',
        }
        values.update(kwargs)
        return self.env['ibs.hr.loan'].create(values)

    def test_schedule_sums_to_the_loan_amount(self):
        """Rounding must not leave a stray balance outstanding forever."""
        loan = self._loan(amount=1000.0, months=3)
        loan.action_approve()
        self.assertEqual(len(loan.line_ids), 3)
        self.assertAlmostEqual(
            sum(loan.line_ids.mapped('amount')), 1000.0, places=2)

    def test_last_instalment_absorbs_the_remainder(self):
        loan = self._loan(amount=1000.0, months=3)
        loan.action_approve()
        amounts = loan.line_ids.sorted('sequence').mapped('amount')
        self.assertAlmostEqual(amounts[0], 333.33, places=2)
        self.assertAlmostEqual(amounts[-1], 333.34, places=2)

    def test_instalment_deducted_on_the_payslip(self):
        loan = self._loan(amount=1200.0, months=4)
        loan.action_approve()
        slip = self._payslip(month=6, year=2026)
        slip.action_compute()
        self.assertAlmostEqual(slip.loan, 300.0, places=2)

    def test_confirming_marks_the_instalment_paid(self):
        loan = self._loan(amount=1200.0, months=4)
        loan.action_approve()
        slip = self._payslip(month=6, year=2026)
        slip.action_compute()
        slip.action_confirm()
        self.assertAlmostEqual(loan.paid_amount, 300.0, places=2)
        self.assertAlmostEqual(loan.balance, 900.0, places=2)

    def test_resetting_a_payslip_releases_the_instalment(self):
        loan = self._loan(amount=1200.0, months=4)
        loan.action_approve()
        slip = self._payslip(month=6, year=2026)
        slip.action_compute()
        slip.action_confirm()
        slip.action_reset()
        self.assertAlmostEqual(loan.paid_amount, 0.0, places=2)
        self.assertAlmostEqual(loan.balance, 1200.0, places=2)

    def test_advance_must_be_single_instalment(self):
        with self.assertRaises(ValidationError):
            self._loan(amount=500.0, months=3, is_advance=True)

    def test_negative_amount_rejected(self):
        with self.assertRaises(ValidationError):
            self._loan(amount=-100.0)

    def test_cancelling_leaves_paid_lines_alone(self):
        loan = self._loan(amount=1200.0, months=4)
        loan.action_approve()
        slip = self._payslip(month=6, year=2026)
        slip.action_compute()
        slip.action_confirm()
        loan.action_cancel()
        paid = loan.line_ids.filtered(lambda l: l.state == 'paid')
        self.assertEqual(len(paid), 1)
