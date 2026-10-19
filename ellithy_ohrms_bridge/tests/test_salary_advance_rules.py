from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSalaryAdvanceRules(EllithyBridgeCommon):
    """CR 2.18 / 2.19 on ``salary.advance``.

    The fixture pays 3,000 basic, so a day is worth 100 and the earned figure
    on the 10th of a month is exactly 1,000.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # HR Admin is the only role that may waive the ceiling; HR Personnel
        # (``cls.hr_user``) raises requests but cannot grant the exception.
        cls.hr_admin = cls.env['res.users'].create({
            'name': 'HR Admin',
            'login': 'bridge.hr.admin',
            'groups_id': [(4, cls.env.ref(
                'ellithy_hr_base.group_ellithy_hr_admin').id)],
        })

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

    def test_the_thirty_first_is_worth_no_more_than_the_thirtieth(self):
        """The basis is a thirty-day month, so day 31 does not overpay."""
        advance = self._advance(date='2026-07-31', advance=3000.0)
        self.assertAlmostEqual(advance.earned_to_date, 3000.0, places=2)
        with self.assertRaises(ValidationError):
            self._advance(date='2026-07-31', advance=3000.01)

    def test_a_mid_month_joiner_earns_only_from_their_start_date(self):
        """Hired on the 15th, six days are earned by the 20th -- not twenty."""
        joiner = self.env['hr.employee'].create({
            'name': 'Mid Month Joiner', 'branch_id': self.branch.id,
            'joining_date': '2026-06-15'})
        self.env['hr.contract'].create({
            'name': 'Joiner Contract', 'employee_id': joiner.id,
            'wage': 3000.0, 'date_start': '2026-06-15', 'state': 'open'})
        advance = self._advance(
            employee_id=joiner.id, date='2026-06-20', advance=600.0)
        self.assertAlmostEqual(advance.earned_to_date, 600.0, places=2)
        with self.assertRaises(ValidationError):
            self._advance(
                employee_id=joiner.id, date='2026-06-20', advance=600.01)

    def test_a_contract_that_has_not_started_yet_earns_nothing(self):
        """``_ibs_contract_on`` falls back to the latest contract; a future
        one is not a salary already being earned against."""
        joiner = self.env['hr.employee'].create({
            'name': 'Not Started', 'branch_id': self.branch.id,
            'joining_date': '2026-06-15'})
        self.env['hr.contract'].create({
            'name': 'Future Contract', 'employee_id': joiner.id,
            'wage': 3000.0, 'date_start': '2026-06-15', 'state': 'open'})
        with self.assertRaises(ValidationError):
            self._advance(employee_id=joiner.id, date='2026-06-10')

    def test_an_expired_contract_is_not_a_salary_source(self):
        """The fallback to the latest contract must not revive ended pay."""
        leaver = self.env['hr.employee'].create({
            'name': 'Contract Ended', 'branch_id': self.branch.id,
            'joining_date': '2023-01-01'})
        self.env['hr.contract'].create({
            'name': 'Ended Contract', 'employee_id': leaver.id,
            'wage': 3000.0, 'date_start': '2023-01-01',
            'date_end': '2026-05-31', 'state': 'close'})
        advance = self.env['salary.advance'].new({
            'employee_id': leaver.id, 'date': '2026-06-10'})
        self.assertAlmostEqual(advance.earned_to_date, 0.0, places=2)
        with self.assertRaises(ValidationError):
            self._advance(employee_id=leaver.id, date='2026-06-10')

    # ---- CR 2.19: the request date is bounded by today ----------------
    def test_a_future_dated_advance_is_refused(self):
        """Otherwise a request dated the 30th borrows a full month on the 8th."""
        with self.assertRaises(ValidationError):
            self._advance(date='2099-06-30', advance=3000.0)

    def test_a_negative_advance_is_refused(self):
        with self.assertRaises(ValidationError):
            self._advance(advance=-100.0)

    def test_an_employee_without_a_contract_cannot_be_advanced(self):
        other = self.env['hr.employee'].create({
            'name': 'No Contract', 'branch_id': self.branch.id})
        with self.assertRaises(ValidationError):
            self._advance(employee_id=other.id)

    # ---- CR 2.19: the HR Admin exception ------------------------------
    def test_hr_admin_may_allow_an_advance_above_the_ceiling(self):
        """1,000 is earned by the 10th; the exception lets 3,000 through."""
        advance = self._advance(
            user=self.hr_admin, advance=3000.0, exceed_condition=True)
        self.assertAlmostEqual(advance.advance, 3000.0, places=2)
        self.assertAlmostEqual(advance.earned_to_date, 1000.0, places=2)

    def test_hr_personnel_may_not_grant_the_exception(self):
        """Gated on the record, so the ORM is no way around the group."""
        with self.assertRaises(ValidationError):
            self._advance(
                user=self.hr_user, advance=3000.0, exceed_condition=True)

    def test_the_exception_must_be_asked_for_to_apply(self):
        """HR Admin alone does not lift the ceiling: the box does."""
        with self.assertRaises(ValidationError):
            self._advance(user=self.hr_admin, advance=3000.0)

    def test_withdrawing_the_exception_re_applies_the_ceiling(self):
        advance = self._advance(
            user=self.hr_admin, advance=3000.0, exceed_condition=True)
        with self.assertRaises(ValidationError):
            advance.with_user(self.hr_admin).write({'exceed_condition': False})

    def test_an_exception_cannot_be_enlarged_by_someone_who_cannot_grant_it(self):
        """The waiver covers the amount it was granted for, not a bigger one."""
        advance = self._advance(
            user=self.hr_admin, advance=3000.0, exceed_condition=True)
        with self.assertRaises(ValidationError):
            advance.with_user(self.hr_user).write({'advance': 4000.0})
        advance.with_user(self.hr_admin).write({'advance': 4000.0})
        self.assertAlmostEqual(advance.advance, 4000.0, places=2)

    def test_the_exception_does_not_licence_a_future_date(self):
        """It waives the ceiling, not the guards that are not the ceiling."""
        with self.assertRaises(ValidationError):
            self._advance(user=self.hr_admin, date='2099-06-30',
                          advance=3000.0, exceed_condition=True)

    def test_the_exception_does_not_licence_a_negative_amount(self):
        with self.assertRaises(ValidationError):
            self._advance(
                user=self.hr_admin, advance=-100.0, exceed_condition=True)

    # ---- CR 2.18 -----------------------------------------------------
    def test_hr_may_raise_an_advance(self):
        advance = self._advance(user=self.hr_user)
        self.assertTrue(advance.id)

    def test_self_service_may_not_raise_an_advance_for_someone_else(self):
        with self.assertRaises(ValidationError):
            self._advance(user=self.plain_user)

    # ---- HR letter item 21 -------------------------------------------
    def test_an_employee_raises_and_submits_their_own_advance(self):
        advance = self._advance(user=self.plain_user,
                                employee_id=self.plain_employee.id)
        self.assertEqual(advance.employee_id, self.plain_employee)
        self.assertFalse(advance.is_hr_user)
        advance.with_user(self.plain_user).action_submit_to_manager()
        self.assertEqual(advance.state, 'submit')

    def test_the_request_defaults_to_the_users_own_employee(self):
        advance = self.env['salary.advance'].with_user(self.plain_user).create({
            'date': '2026-06-10', 'advance': 300.0})
        self.assertEqual(advance.employee_id, self.plain_employee)

    def test_an_employee_cannot_approve_their_own_advance(self):
        advance = self._advance(user=self.plain_user,
                                employee_id=self.plain_employee.id)
        advance.with_user(self.plain_user).action_submit_to_manager()
        with self.assertRaises(ValidationError):
            advance.with_user(self.plain_user).write({'state': 'waiting_approval'})
