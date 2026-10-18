from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestClearanceRound(EllithyBridgeCommon):
    """CR 2.10 -- the clearance form as a round of department sign-offs,
    run after the exit is approved, on the employee's actual last working
    day."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.dept_stores = cls.env['hr.department'].create({'name': 'Stores'})

    def _approved(self, **kwargs):
        """An exit taken all the way to 'approved', dated for today --
        clearance can only start once both of those are true."""
        values = {
            'employee_id': self.employee.id,
            'expected_revealing_date': fields.Date.today(),
            'reason': 'Relocating.',
            'resignation_type': 'resigned',
            'departure_reason_id': self.env.ref('hr.departure_resigned').id,
        }
        values.update(kwargs)
        resignation = self.env['hr.resignation'].create(values)
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        resignation.action_approve_resignation()
        return resignation

    def _start(self, resignation, departments=None, last_day=None):
        wizard = self.env['hr.resignation.clearance.wizard'].create({
            'resignation_id': resignation.id,
            'last_working_day': (
                last_day or resignation.expected_revealing_date),
            'department_ids': [(6, 0, (
                departments or (self.dept_it | self.dept_finance)).ids)],
        })
        wizard.action_start_clearance()
        return resignation.clearance_line_ids

    # ---- starting -----------------------------------------------------
    def test_clearance_starts_from_the_wizard_not_on_approval(self):
        resignation = self._approved()
        self.assertEqual(resignation.clearance_state, 'none')
        self.assertFalse(resignation.clearance_line_ids)
        self._start(resignation)
        self.assertEqual(resignation.clearance_state, 'progress')
        self.assertEqual(len(resignation.clearance_line_ids), 2)
        self.assertEqual(resignation.clearance_progress, '0 / 2')

    def test_the_wizard_refuses_a_last_working_day_other_than_today(self):
        resignation = self._approved()
        with self.assertRaises(ValidationError):
            self._start(resignation,
                        last_day=fields.Date.today() + timedelta(days=1))

    def test_adding_departments_later_does_not_re_check_the_date(self):
        """The "must be today" gate is only for the very first opening --
        topping up an already-started clearance a day or two later should
        not start refusing."""
        resignation = self._approved()
        self._start(resignation, self.dept_it)
        later = fields.Date.today() + timedelta(days=3)
        self._start(resignation, self.dept_it | self.dept_stores,
                    last_day=later)
        self.assertEqual(resignation.expected_revealing_date, later)
        self.assertEqual(len(resignation.clearance_line_ids), 2)

    def test_the_wizard_defaults_to_the_date_already_on_the_request(self):
        resignation = self._approved()
        wizard = self.env['hr.resignation.clearance.wizard'].create(
            {'resignation_id': resignation.id,
             'department_ids': [(6, 0, self.dept_it.ids)]})
        self.assertEqual(wizard.last_working_day,
                         resignation.expected_revealing_date)

    def test_the_last_day_cannot_precede_the_joining_date(self):
        resignation = self._approved()
        with self.assertRaises(ValidationError):
            self._start(resignation,
                        last_day=self.employee.joining_date - timedelta(days=1))

    def test_departments_can_be_added_without_losing_signatures(self):
        resignation = self._approved()
        lines = self._start(resignation, self.dept_it)
        lines.action_approve()
        self.assertEqual(lines.state, 'approved')

        self._start(resignation, self.dept_it | self.dept_stores)
        self.assertEqual(len(resignation.clearance_line_ids), 2)
        # The IT signature survived the second pass.
        self.assertEqual(lines.state, 'approved')
        self.assertEqual(resignation.clearance_progress, '1 / 2')

    def test_a_department_appears_once(self):
        resignation = self._approved()
        self._start(resignation, self.dept_it)
        with self.assertRaises(Exception):
            self.env['hr.resignation.clearance'].create({
                'resignation_id': resignation.id,
                'department_id': self.dept_it.id,
            })

    def test_a_suspension_has_no_clearance(self):
        suspension = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'request_type': 'suspension',
            'reason': 'Under investigation.',
            'suspension_start': fields.Date.today(),
        })
        with self.assertRaises(ValidationError):
            suspension.action_open_clearance_wizard()

    def test_clearance_cannot_start_before_approval(self):
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'expected_revealing_date': fields.Date.today(),
            'reason': 'Relocating.',
            'resignation_type': 'resigned',
            'departure_reason_id': self.env.ref('hr.departure_resigned').id,
        })
        resignation.action_confirm_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_open_clearance_wizard()
        resignation.action_endorse_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_open_clearance_wizard()

    # ---- who signed, and when -----------------------------------------
    def test_each_department_records_its_own_signature(self):
        resignation = self._approved()
        lines = self._start(resignation)
        it_line = lines.filtered(lambda l: l.department_id == self.dept_it)
        it_line.action_approve()

        self.assertEqual(it_line.state, 'approved')
        self.assertEqual(it_line.approved_by, self.env.user)
        self.assertTrue(it_line.approved_at)
        # The other department is untouched.
        other = lines - it_line
        self.assertEqual(other.state, 'pending')
        self.assertFalse(other.approved_by)
        self.assertEqual(resignation.clearance_progress, '1 / 2')

    def test_departments_may_sign_in_any_order(self):
        resignation = self._approved()
        lines = self._start(resignation)
        lines[1].action_approve()
        lines[0].action_approve()
        self.assertTrue(resignation.clearance_complete)

    def test_a_department_can_block_with_a_reason(self):
        resignation = self._approved()
        lines = self._start(resignation)
        blocked = lines[0]
        with self.assertRaises(ValidationError):
            blocked.action_reject()
        blocked.rejection_reason = 'Laptop not returned.'
        blocked.action_reject()
        self.assertEqual(blocked.state, 'rejected')
        self.assertTrue(blocked.approved_by)

    def test_outstanding_amounts_are_totalled_for_the_settlement(self):
        resignation = self._approved()
        lines = self._start(resignation)
        lines[0].amount_due = 250.0
        lines[1].amount_due = 100.0
        self.assertAlmostEqual(resignation.clearance_total_due, 350.0, places=2)

    def test_a_signature_can_be_reset(self):
        resignation = self._approved()
        lines = self._start(resignation)
        lines[0].action_approve()
        lines[0].action_reset()
        self.assertEqual(lines[0].state, 'pending')
        self.assertFalse(lines[0].approved_by)

    # ---- the final confirmation ---------------------------------------
    def test_confirming_needs_every_department(self):
        resignation = self._approved()
        lines = self._start(resignation)
        lines[0].action_approve()
        with self.assertRaises(ValidationError):
            resignation.action_confirm_clearance()
        lines[1].action_approve()
        resignation.action_confirm_clearance()
        self.assertEqual(resignation.clearance_state, 'done')
        self.assertEqual(resignation.clearance_confirmed_by, self.env.user)
        self.assertTrue(resignation.clearance_confirmed_at)

    def test_a_blocked_department_stops_the_confirmation(self):
        resignation = self._approved()
        lines = self._start(resignation)
        lines[0].action_approve()
        lines[1].rejection_reason = 'Advance outstanding.'
        lines[1].action_reject()
        with self.assertRaises(ValidationError):
            resignation.action_confirm_clearance()

    def test_clearance_cannot_be_confirmed_before_it_starts(self):
        resignation = self._approved()
        with self.assertRaises(ValidationError):
            resignation.action_confirm_clearance()

    def test_clearance_completes_after_the_exit_is_already_approved(self):
        resignation = self._approved()
        self.assertEqual(resignation.state, 'approved')
        self._start(resignation).action_approve()
        resignation.action_confirm_clearance()
        self.assertEqual(resignation.clearance_state, 'done')
        # Approving does not run twice, and the resignation's own state is
        # untouched by clearance finishing.
        self.assertEqual(resignation.state, 'approved')

    def test_clearance_can_be_reopened_once_confirmed(self):
        resignation = self._approved()
        self._start(resignation).action_approve()
        resignation.action_confirm_clearance()
        resignation.action_reopen_clearance()
        self.assertEqual(resignation.clearance_state, 'progress')
        self.assertFalse(resignation.clearance_confirmed_by)

    # ---- who may see or sign a clearance line --------------------------
    def test_the_leaver_cannot_see_clearance_before_it_is_signed(self):
        resignation = self._approved(employee_id=self.plain_employee.id)
        self._start(resignation)
        visible = self.env['hr.resignation.clearance'].with_user(
            self.plain_user).search([('resignation_id', '=', resignation.id)])
        self.assertFalse(visible)

    def test_approval_disconnects_the_login_before_clearance_can_start(self):
        """Flagged rather than left a silent gap: ``_apply_employee_exit``
        (run by approval, which now always comes before clearance) clears
        and disables the employee's login for a real exit. By the time
        clearance finishes there is no login left for "the employee sees
        their own completed clearance" to ever apply to -- see the summary
        given alongside this change for the follow-up decision this raises.
        """
        resignation = self._approved(employee_id=self.plain_employee.id)
        self.plain_employee.invalidate_recordset()
        self.assertFalse(self.plain_employee.user_id)
        self.plain_user.invalidate_recordset()
        self.assertFalse(self.plain_user.active)

    def test_a_department_manager_sees_only_their_own_departments_line(self):
        it_manager = self.env['res.users'].create({
            'name': 'IT Manager', 'login': 'bridge.it.manager',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        self.dept_it.manager_id = it_manager.employee_id
        resignation = self._approved()
        self._start(resignation)
        visible = self.env['hr.resignation.clearance'].with_user(
            it_manager).search([('resignation_id', '=', resignation.id)])
        self.assertEqual(visible.department_id, self.dept_it)

    def test_a_bystander_cannot_sign_by_writing_state_directly(self):
        bystander = self.env['res.users'].create({
            'name': 'Bystander', 'login': 'bridge.bystander',
            'groups_id': [(6, 0, [self.env.ref('base.group_user').id])],
        })
        resignation = self._approved()
        lines = self._start(resignation)
        with self.assertRaises(ValidationError):
            lines[0].with_user(bystander).write({'state': 'approved'})
