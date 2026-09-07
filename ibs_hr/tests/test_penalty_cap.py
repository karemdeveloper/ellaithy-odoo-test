from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestPenaltyCap(IbsHrCommon):
    """CR 2.12 -- five days a month, the rest carried over.

    The fixture pays 3,000 basic, so a day is worth exactly 100 and the
    arithmetic below reads directly as days.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A single-rung ladder: the penalty days are set per warning below,
        # so the ladder itself must not interfere.
        cls.violation = cls.env['ibs.hr.violation'].create({
            'name': 'Serious misconduct',
            'code': 'V999',
            'penalty_ids': [
                (0, 0, {'occurrence': 1, 'action': 'fine',
                        'penalty_days': 1.0}),
            ],
        })

    def _penalty(self, days, month=6, day=1):
        warning = self.env['ibs.hr.warning'].create({
            'employee_id': self.employee.id,
            'violation_id': self.violation.id,
            'date': f'2026-{month:02d}-{day:02d}',
            'custom_penalty_days': days,
        })
        warning.action_submit()
        warning.action_approve()
        return warning

    def test_execution_date_defaults_to_the_violation_date(self):
        warning = self._penalty(1.0, month=6, day=9)
        self.assertEqual(str(warning.execution_date), '2026-06-09')

    def test_a_penalty_within_the_ceiling_is_taken_whole(self):
        warning = self._penalty(3.0)
        slip = self._payslip(month=6)
        self.assertAlmostEqual(slip.penalty_days_taken, 3.0, places=2)
        self.assertAlmostEqual(slip.penalty_days_deferred, 0.0, places=2)
        slip.action_payslip_done()
        self.assertTrue(warning.is_settled)

    def test_a_penalty_above_the_ceiling_is_capped_and_carried(self):
        warning = self._penalty(8.0)
        june = self._payslip(month=6)
        self.assertAlmostEqual(june.penalty_days_taken, 5.0, places=2)
        self.assertAlmostEqual(june.penalty_days_deferred, 3.0, places=2)
        self.assertAlmostEqual(june.penalty_amount, 500.0, places=2)

        june.action_payslip_done()
        self.assertFalse(warning.is_settled)
        self.assertAlmostEqual(warning.days_settled, 5.0, places=2)
        self.assertAlmostEqual(warning.days_remaining, 3.0, places=2)
        # A part-paid penalty must not claim to have been settled by June.
        self.assertFalse(warning.payslip_id)

        july = self._payslip(month=7)
        self.assertAlmostEqual(july.penalty_days_taken, 3.0, places=2)
        july.action_payslip_done()
        self.assertTrue(warning.is_settled)
        self.assertEqual(warning.payslip_id, july)

    def test_the_ceiling_is_shared_across_several_penalties(self):
        """Two penalties totalling seven days still cost five this month."""
        first = self._penalty(4.0, day=1)
        second = self._penalty(3.0, day=2)
        june = self._payslip(month=6)
        self.assertAlmostEqual(june.penalty_days_taken, 5.0, places=2)
        self.assertAlmostEqual(june.penalty_days_deferred, 2.0, places=2)

        june.action_payslip_done()
        # Oldest first: the four-day penalty clears, the newer one is part-paid.
        self.assertTrue(first.is_settled)
        self.assertFalse(second.is_settled)
        self.assertAlmostEqual(second.days_remaining, 2.0, places=2)

    def test_a_deferred_penalty_is_taken_before_a_newer_one(self):
        old = self._penalty(8.0, month=6, day=1)
        june = self._payslip(month=6)
        june.action_payslip_done()

        new = self._penalty(4.0, month=7, day=1)
        july = self._payslip(month=7)
        july.action_payslip_done()

        self.assertTrue(old.is_settled)
        # July's budget: 3 days of arrears, then 2 of the new four-day penalty.
        self.assertAlmostEqual(new.days_settled, 2.0, places=2)
        self.assertAlmostEqual(new.days_remaining, 2.0, places=2)

    def test_the_ceiling_is_a_parameter_not_a_constant(self):
        self.env['ir.config_parameter'].sudo().set_param(
            'ibs_hr.max_penalty_days_per_month', '2')
        self._penalty(8.0)
        june = self._payslip(month=6)
        self.assertAlmostEqual(june.penalty_days_taken, 2.0, places=2)
        self.assertAlmostEqual(june.penalty_days_deferred, 6.0, places=2)

    def test_a_penalty_deferred_to_a_later_month_is_not_taken_early(self):
        """CR 2.11 -- payroll selects on the execution date."""
        warning = self._penalty(2.0, month=6, day=1)
        warning.execution_date = '2026-07-01'
        june = self._payslip(month=6)
        self.assertEqual(june.penalty_days_taken, 0.0)
        july = self._payslip(month=7)
        self.assertAlmostEqual(july.penalty_days_taken, 2.0, places=2)
