from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestPayrollEngine(IbsHrCommon):

    def test_daily_rate_is_wage_over_30(self):
        """Verified against 3,174 legacy rows: the divisor is 30, not the
        calendar month length."""
        slip = self._payslip(month=2, year=2026)  # 28-day month
        slip.action_compute()
        self.assertEqual(slip.calculation_days, 30.0)
        self.assertAlmostEqual(slip.daily_rate, 100.0, places=2)

    def test_period_dates_span_the_month(self):
        slip = self._payslip(month=2, year=2026)
        self.assertEqual(str(slip.date_from), '2026-02-01')
        self.assertEqual(str(slip.date_to), '2026-02-28')
        leap = self._payslip(month=2, year=2028)
        self.assertEqual(str(leap.date_to), '2028-02-29')

    def test_net_equals_allowance_minus_deduction(self):
        """The one invariant that holds on 9,959 of 9,976 legacy rows."""
        slip = self._payslip()
        slip.action_compute()
        self.assertAlmostEqual(
            slip.net_salary,
            slip.total_allowance - slip.total_deduction, places=2)

    def test_insurance_is_11pc_of_subscription_wage(self):
        slip = self._payslip()
        slip.action_compute()
        self.assertAlmostEqual(slip.insurance_employee_share, 220.0, places=2)

    def test_insurance_skipped_when_not_enrolled(self):
        self.employee.has_social_insurance = False
        slip = self._payslip()
        slip.action_compute()
        self.assertEqual(slip.insurance_employee_share, 0.0)

    def test_insurance_always_counts_toward_total_deduction(self):
        """Departure from legacy, which includes it on 5,112 rows and omits it
        on 3,408 with no rule. Always including it is the consistent reading."""
        slip = self._payslip()
        slip.action_compute()
        self.assertGreater(slip.insurance_employee_share, 0.0)
        self.assertAlmostEqual(
            slip.total_deduction,
            sum(slip[f] for f in [
                'absence_penalty', 'late_penalty', 'early_leave_penalty',
                'unachieved_hours_penalty', 'misconduct_penalty',
                'single_fingerprint_penalty', 'deduction_leave',
                'mobile_deduction', 'medical_deduction', 'loan',
                'extra_deduction', 'id_card_deduction', 'admin_penalty',
                'insurance_employee_share']), places=2)

    def test_absence_deducts_one_day_per_absent_day(self):
        self._day(1, state='absent')
        self._day(2, state='absent')
        slip = self._payslip()
        slip.action_compute()
        self.assertAlmostEqual(slip.absence_days, 2.0, places=2)
        self.assertAlmostEqual(slip.absence_penalty, 200.0, places=2)

    def test_absence_days_is_a_day_count_not_money(self):
        """Guards the legacy defect: their absence_days column holds the money
        value, identical to absence_penalty on 2,915 of 3,174 rows."""
        self._day(1, state='absent')
        slip = self._payslip()
        slip.action_compute()
        self.assertEqual(slip.absence_days, 1.0)
        self.assertNotEqual(slip.absence_days, slip.absence_penalty)

    def test_unpaid_leave_counts_as_absence_paid_does_not(self):
        self._day(1, state='leave', is_paid_leave=True)
        self._day(2, state='leave', is_paid_leave=False)
        slip = self._payslip()
        slip.action_compute()
        self.assertAlmostEqual(slip.absence_days, 1.0, places=2)

    def test_weekend_and_holiday_never_deduct(self):
        self._day(6, state='weekend')
        self._day(7, state='holiday')
        slip = self._payslip()
        slip.action_compute()
        self.assertEqual(slip.absence_days, 0.0)
        self.assertEqual(slip.absence_penalty, 0.0)

    def test_joining_difference_excluded_from_total(self):
        """Matches legacy: 9,504 of 9,976 rows exclude it from the total."""
        slip = self._payslip()
        slip.action_compute()
        before = slip.total_allowance
        slip.joining_difference = 500.0
        self.assertAlmostEqual(slip.total_allowance, before, places=2)

    def test_one_payslip_per_employee_per_month(self):
        self._payslip()
        with self.assertRaises(Exception):
            self._payslip()
            self.env.flush_all()

    def test_confirmed_payslip_cannot_be_recomputed(self):
        slip = self._payslip()
        slip.action_compute()
        slip.action_confirm()
        with self.assertRaises(ValidationError):
            slip.action_compute()

    def test_recompute_uses_contract_in_force_not_latest(self):
        """A June payslip must not pick up a July raise.

        The old contract has to be closed before the new one is created --
        hr_contract refuses two overlapping running contracts, which is
        itself worth knowing when writing the migration.
        """
        self.contract.date_end = '2026-06-30'
        self.env['hr.contract'].create({
            'name': 'Raise',
            'employee_id': self.employee.id,
            'wage': 9000.0,
            'date_start': '2026-07-01',
            'state': 'open',
        })
        slip = self._payslip(month=6, year=2026)
        slip.action_compute()
        self.assertAlmostEqual(slip.base_salary, 3000.0, places=2)

    def test_rejects_impossible_month(self):
        with self.assertRaises(ValidationError):
            self._payslip(month=13)
