from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestResignationFlow(EllithyBridgeCommon):
    """CR 2.7 / 2.8 / 2.9 / 2.10 on ``hr.resignation``."""

    def _clear(self, resignation, departments=None):
        """Run a resignation through clearance: start, sign, confirm."""
        wizard = self.env['hr.resignation.clearance.wizard'].create({
            'resignation_id': resignation.id,
            'last_working_day': resignation.expected_revealing_date,
            'department_ids': [(6, 0, (
                departments or (self.dept_it | self.dept_finance)).ids)],
        })
        wizard.action_start_clearance()
        resignation.clearance_line_ids.action_approve()
        resignation.action_confirm_clearance()
        return resignation

    def _resignation(self, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'expected_revealing_date': '2026-12-31',
            'reason': 'Relocating.',
            'resignation_type': 'resigned',
        }
        values.update(kwargs)
        return self.env['hr.resignation'].create(values)

    # ---- CR 2.9 ------------------------------------------------------
    def test_the_agreed_type_wording(self):
        selection = dict(
            self.env['hr.resignation']._fields['resignation_type']
            ._description_selection(self.env))
        self.assertEqual(selection['resigned'], 'Resignation')
        self.assertEqual(selection['fired'], 'Termination by Company')
        for key in ('mutual', 'contract_end', 'retirement'):
            self.assertIn(key, selection)

    # ---- CR 2.10 -----------------------------------------------------
    def test_confirming_no_longer_lays_out_a_checklist(self):
        """Clearance is started deliberately, from the wizard."""
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        self.assertFalse(resignation.clearance_line_ids)
        self.assertEqual(resignation.clearance_state, 'none')

    def test_approval_is_blocked_until_clearance_is_confirmed(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_approve_resignation()
        self._clear(resignation)
        self.assertEqual(resignation.clearance_state, 'done')
        resignation.action_approve_resignation()
        self.assertEqual(resignation.state, 'approved')

    # ---- CR 2.8 ------------------------------------------------------
    def test_hr_cannot_approve_before_the_manager_endorses(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        self._clear(resignation)
        with self.assertRaises(ValidationError):
            resignation.action_approve_resignation()

    def test_the_cycle_records_who_endorsed_and_who_approved(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        self.assertEqual(resignation.state, 'endorsed')
        self.assertEqual(resignation.endorsed_by, self.env.user)
        self._clear(resignation)
        resignation.action_approve_resignation()
        self.assertEqual(resignation.approved_by, self.env.user)

    def test_rejecting_requires_a_reason(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_reject_resignation()
        resignation.rejection_reason = 'Notice period not served.'
        resignation.action_reject_resignation()
        self.assertEqual(resignation.state, 'cancel')

    # ---- leaving the company -----------------------------------------
    def _approved_past_dated(self):
        """A resignation whose last day has already passed."""
        yesterday = fields.Date.today() - timedelta(days=1)
        resignation = self._resignation(expected_revealing_date=yesterday)
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        self._clear(resignation)
        return resignation

    def test_approving_a_past_dated_exit_archives_the_employee(self):
        """The case that could not work before.

        ellithy_hr_base refuses to archive without both exit dates and
        refuses to let an active employee hold them, so the stock approval's
        bare ``active = False`` was rejected outright.
        """
        resignation = self._approved_past_dated()
        resignation.action_approve_resignation()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)
        self.assertEqual(self.employee.last_working_day,
                         resignation.expected_revealing_date)
        self.assertTrue(self.employee.resignation_date)
        self.assertEqual(self.employee.resignation_type, 'resignation')
        self.assertEqual(self.employee.inactive_type, 'resignation')
        self.assertTrue(self.employee.departure_reason_id)

    def test_a_future_dated_exit_leaves_the_employee_active(self):
        resignation = self._resignation(
            expected_revealing_date=fields.Date.today() + timedelta(days=30))
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        self._clear(resignation)
        resignation.action_approve_resignation()
        self.assertTrue(self.employee.active)
        self.assertFalse(self.employee.last_working_day)

    def test_the_cron_archives_a_leaver_once_the_day_arrives(self):
        """``update_employee_status`` is what the daily cron calls. It was
        never defined by the vendor, so an exit dated ahead was never acted
        on."""
        resignation = self._resignation(
            expected_revealing_date=fields.Date.today() + timedelta(days=30))
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        self._clear(resignation)
        resignation.action_approve_resignation()
        self.assertTrue(self.employee.active)

        # The day arrives.
        resignation.write({
            'expected_revealing_date': fields.Date.today() - timedelta(days=1),
            'approved_revealing_date': fields.Date.today() - timedelta(days=1),
        })
        self.env['hr.resignation'].update_employee_status()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)

    def test_the_cron_is_safe_to_run_twice(self):
        resignation = self._approved_past_dated()
        resignation.action_approve_resignation()
        self.env['hr.resignation'].update_employee_status()
        self.env['hr.resignation'].update_employee_status()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)

    def test_resetting_to_draft_reactivates_and_clears_the_exit(self):
        resignation = self._approved_past_dated()
        resignation.action_approve_resignation()
        resignation.action_reset_to_draft()
        self.employee.invalidate_recordset()
        self.assertTrue(self.employee.active)
        self.assertFalse(self.employee.last_working_day)
        self.assertFalse(self.employee.resignation_date)

    def test_a_dismissal_is_recorded_as_one(self):
        resignation = self._approved_past_dated()
        resignation.resignation_type = 'fired'
        resignation.action_approve_resignation()
        self.employee.invalidate_recordset()
        self.assertEqual(self.employee.resignation_type,
                         'termination_of_service')
        self.assertEqual(self.employee.inactive_type, 'termination')
        self.assertTrue(self.employee.fired)
        self.assertFalse(self.employee.resigned)

    # ---- CR 2.7 ------------------------------------------------------
    def test_the_employee_reaches_the_resignation_by_smart_button(self):
        resignation = self._resignation()
        self.assertEqual(self.employee.resignation_count, 1)
        action = self.employee.action_view_resignations()
        self.assertEqual(action['res_model'], 'hr.resignation')
        # A single record opens straight onto its own form.
        self.assertEqual(action['res_id'], resignation.id)
