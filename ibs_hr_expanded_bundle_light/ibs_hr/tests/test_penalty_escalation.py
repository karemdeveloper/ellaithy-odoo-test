from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestPenaltyEscalation(IbsHrCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The real ladder for "lateness up to 15 minutes without permission",
        # migrated from violation_penalties: warning, then 0.25/0.50/1.00 days.
        cls.violation = cls.env['ibs.hr.violation'].create({
            'name': 'Lateness up to 15 minutes without permission',
            'code': 'V001',
            'penalty_ids': [
                (0, 0, {'occurrence': 1, 'action': 'warning', 'penalty_days': 0.0}),
                (0, 0, {'occurrence': 2, 'action': 'fine', 'penalty_days': 0.25}),
                (0, 0, {'occurrence': 3, 'action': 'fine', 'penalty_days': 0.50}),
                (0, 0, {'occurrence': 4, 'action': 'fine', 'penalty_days': 1.00}),
            ],
        })

    def _warn(self, day, month=6, approve=True):
        warning = self.env['ibs.hr.warning'].create({
            'employee_id': self.employee.id,
            'violation_id': self.violation.id,
            'date': f'2026-{month:02d}-{day:02d}',
        })
        if approve:
            warning.action_submit()
            warning.action_approve()
        return warning

    def test_first_offence_is_a_warning_with_no_deduction(self):
        warning = self._warn(1)
        self.assertEqual(warning.occurrence, 1)
        self.assertEqual(warning.action, 'warning')
        self.assertEqual(warning.deducted_amount, 0.0)

    def test_ladder_escalates_across_occurrences(self):
        self._warn(1)
        self._warn(2)
        third = self._warn(3)
        self.assertEqual(third.occurrence, 3)
        self.assertAlmostEqual(third.penalty_days, 0.50, places=2)
        self.assertAlmostEqual(third.deducted_amount, 50.0, places=2)

    def test_fifth_offence_stays_on_the_top_rung(self):
        """The ladder stops at four. A fifth offence must not fall through to
        no penalty at all."""
        for day in range(1, 5):
            self._warn(day)
        fifth = self._warn(5)
        self.assertEqual(fifth.occurrence, 5)
        self.assertAlmostEqual(fifth.penalty_days, 1.00, places=2)

    def test_only_approved_warnings_count_toward_occurrence(self):
        self._warn(1, approve=False)
        second = self._warn(2)
        self.assertEqual(second.occurrence, 1)

    def test_occurrence_resets_outside_the_window(self):
        """Reset window is a CONFIGURED ASSUMPTION, not a migrated rule -- the
        legacy database carries no reset logic. Confirm with HR."""
        self.env['ir.config_parameter'].sudo().set_param(
            'ibs_hr.violation_reset_months', '12')
        old = self.env['ibs.hr.warning'].create({
            'employee_id': self.employee.id,
            'violation_id': self.violation.id,
            'date': '2024-01-15',
        })
        old.action_submit()
        old.action_approve()
        fresh = self._warn(1)
        self.assertEqual(fresh.occurrence, 1)

    def test_override_beats_the_ladder(self):
        warning = self._warn(1)
        warning.custom_penalty_days = 2.0
        self.assertAlmostEqual(warning.penalty_days, 2.0, places=2)
        self.assertAlmostEqual(warning.deducted_amount, 200.0, places=2)

    def test_non_monetary_action_cannot_carry_days(self):
        with self.assertRaises(ValidationError):
            self.env['ibs.hr.violation.penalty'].create({
                'violation_id': self.violation.id,
                'occurrence': 9,
                'action': 'dismissal',
                'penalty_days': 3.0,
            })

    def test_duplicate_occurrence_rejected(self):
        with self.assertRaises(ValidationError):
            self.violation.write({'penalty_ids': [
                (0, 0, {'occurrence': 2, 'action': 'fine', 'penalty_days': 1.0})]})

    def test_rejection_requires_a_comment(self):
        warning = self._warn(1, approve=False)
        warning.action_submit()
        with self.assertRaises(ValidationError):
            warning.action_reject()

    def test_hr_without_approver_group_cannot_approve(self):
        """CR 2.13 -- only the named approver group may decide a warning."""
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Warning HR author', 'login': 'warning.hr.author',
            'groups_id': [(6, 0, [self.env.ref(
                'ibs_hr.penalty_generalist').id])]})
        warning = self._warn(1, approve=False).with_user(user)
        warning.action_submit()
        self.assertFalse(user.has_group(
            'ibs_hr.group_ibs_admin_penalty_approver'))
        with self.assertRaises(ValidationError):
            warning.action_approve()

    def test_approved_warnings_reach_the_payslip(self):
        self._warn(1)
        self._warn(2)
        slip = self._payslip(month=6)
        # 0 days for the first offence, 0.25 for the second, at 100/day.
        self.assertAlmostEqual(slip.penalty_amount, 25.0, places=2)
        self.assertAlmostEqual(slip.penalty_days_taken, 0.25, places=2)

    def test_unapproved_warnings_do_not_reach_the_payslip(self):
        self._warn(1, approve=False)
        slip = self._payslip(month=6)
        self.assertEqual(slip.penalty_amount, 0.0)

    def test_a_warning_is_not_deducted_twice(self):
        self._warn(1)
        self._warn(2)
        june = self._payslip(month=6)
        june.action_payslip_done()
        self.assertAlmostEqual(june.penalty_days_taken, 0.25, places=2)
        july = self._payslip(month=7)
        self.assertEqual(july.penalty_days_taken, 0.0)

    def test_resetting_a_payslip_returns_the_days(self):
        """Releasing the booking must make the penalty outstanding again."""
        self._warn(1)
        warning = self._warn(2)
        june = self._payslip(month=6)
        june.action_payslip_done()
        self.assertTrue(warning.is_settled)
        june.action_payslip_draft()
        self.assertFalse(warning.is_settled)
        self.assertAlmostEqual(warning.days_remaining, 0.25, places=2)
