from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestAttendanceDay(IbsHrCommon):

    def test_worked_hours_from_punches(self):
        day = self._day(1, check_in='2026-06-01 09:00:00',
                        check_out='2026-06-01 17:00:00')
        self.assertAlmostEqual(day.worked_hours, 8.0, places=2)

    def test_cross_midnight_shift_computes_positive_hours(self):
        """A night shift ending after midnight must not produce negative or
        zero hours."""
        day = self._day(1, check_in='2026-06-01 22:00:00',
                        check_out='2026-06-02 06:00:00')
        self.assertAlmostEqual(day.worked_hours, 8.0, places=2)

    def test_single_punch_detected(self):
        day = self._day(1, check_in='2026-06-01 09:00:00')
        self.assertTrue(day.single_punch)
        both = self._day(2, check_in='2026-06-02 09:00:00',
                         check_out='2026-06-02 17:00:00')
        self.assertFalse(both.single_punch)

    def test_single_punch_penalised_at_half_a_day(self):
        self._day(1, check_in='2026-06-01 09:00:00')
        slip = self._payslip()
        slip.action_compute()
        self.assertAlmostEqual(slip.single_fingerprint_penalty, 50.0, places=2)

    def test_shortfall_is_floored_at_zero(self):
        """Working longer than scheduled is overtime, never negative
        shortfall."""
        day = self._day(1, scheduled_hours=8.0,
                        check_in='2026-06-01 09:00:00',
                        check_out='2026-06-01 19:00:00')
        self.assertEqual(day.shortfall_hours, 0.0)

    def test_shortfall_only_on_present_days(self):
        day = self._day(1, state='absent', scheduled_hours=8.0)
        self.assertEqual(day.shortfall_hours, 0.0)

    def test_one_day_per_employee_per_date(self):
        self._day(1)
        with self.assertRaises(Exception):
            self._day(1)
            self.env.flush_all()

    def test_totals_for_period_aggregates(self):
        self._day(1, state='absent')
        self._day(2, late_minutes=30)
        self._day(3, check_in='2026-06-03 09:00:00')
        totals = self.env['ibs.hr.attendance.day'].totals_for_period(
            self.employee, '2026-06-01', '2026-06-30')
        self.assertEqual(totals['absence_days'], 1.0)
        self.assertEqual(totals['late_minutes'], 30)
        self.assertEqual(totals['single_punch_count'], 1)
        self.assertEqual(totals['day_count'], 3)

    def test_totals_exclude_other_months(self):
        self._day(1, month=5, state='absent')
        self._day(1, month=6, state='absent')
        totals = self.env['ibs.hr.attendance.day'].totals_for_period(
            self.employee, '2026-06-01', '2026-06-30')
        self.assertEqual(totals['absence_days'], 1.0)
