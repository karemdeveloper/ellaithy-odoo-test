from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSalaryAdvanceRules(EllithyBridgeCommon):
    """CR 2.18 / 2.19 on ``salary.advance``.

    The fixture pays 3,000 basic, so a day is worth 100 and the earned figure
    on the 10th of a month is exactly 1,000.
    """

    def _advance(self, user=None, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'date': '2026-06-10',
            'advance': 500.0,
        }
        values.update(kwargs)
        model = self.env['salary.advance']
        if user:
            model = model.with_user(user)
        return model.create(values)

    # ---- CR 2.19 -----------------------------------------------------
    def test_earned_to_date_is_pay_accrued_since_the_first(self):
        advance = self._advance()
        self.assertAlmostEqual(advance.earned_to_date, 1000.0, places=2)

    def test_an_advance_within_what_was_earned_is_accepted(self):
        advance = self._advance(advance=1000.0)
        self.assertAlmostEqual(advance.advance, 1000.0, places=2)

    def test_an_advance_above_what_was_earned_is_refused(self):
        with self.assertRaises(ValidationError):
            self._advance(advance=1000.01)

    def test_the_ceiling_moves_with_the_date(self):
        """Later in the month, more has been earned."""
        late = self._advance(date='2026-06-25', advance=2500.0)
        self.assertAlmostEqual(late.earned_to_date, 2500.0, places=2)
        with self.assertRaises(ValidationError):
            self._advance(date='2026-06-05', advance=2500.0)

    def test_an_employee_without_a_contract_cannot_be_advanced(self):
        other = self.env['hr.employee'].create({
            'name': 'No Contract', 'branch_id': self.branch.id})
        with self.assertRaises(ValidationError):
            self._advance(employee_id=other.id)

    # ---- CR 2.18 -----------------------------------------------------
    def test_hr_may_raise_an_advance(self):
        advance = self._advance(user=self.hr_user)
        self.assertTrue(advance.id)

    def test_self_service_may_not_raise_an_advance(self):
        with self.assertRaises(ValidationError):
            self._advance(user=self.plain_user)
