import re
from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestResignationFlow(EllithyBridgeCommon):
    """CR 2.7 / 2.8 / 2.9 / 2.10 on ``hr.resignation``."""

    def _clear(self, resignation, departments=None):
        """Run an already-approved exit through clearance: start, sign,
        confirm. The resignation must be approved and dated for today --
        clearance is a post-approval, last-working-day step."""
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

    def test_an_exit_still_needs_a_reason(self):
        with self.assertRaises(ValidationError):
            self._resignation(reason=False)

    def test_a_suspension_does_not_need_a_reason(self):
        """Unlike an exit, a suspension has its own reason already
        (``suspension_reason_id`` / ``suspension_comment``) -- the generic
        "Resignation Details / Reason" field is hidden for one and, since
        the form cannot ask for something it does not show, no longer
        required for one either."""
        suspension = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'request_type': 'suspension',
            'suspension_start': fields.Date.today(),
        })
        self.assertFalse(suspension.reason)

    # ---- CR 2.10 -----------------------------------------------------
    def test_confirming_no_longer_lays_out_a_checklist(self):
        """Clearance is started deliberately, from the wizard."""
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        self.assertFalse(resignation.clearance_line_ids)
        self.assertEqual(resignation.clearance_state, 'none')

    def test_clearance_cannot_start_before_approval(self):
        resignation = self._resignation(
            expected_revealing_date=fields.Date.today())
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_open_clearance_wizard()
        resignation.action_approve_resignation()
        self._clear(resignation)
        self.assertEqual(resignation.clearance_state, 'done')

    def test_clearance_cannot_start_before_the_last_working_day(self):
        resignation = self._resignation(
            expected_revealing_date=fields.Date.today() + timedelta(days=5))
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        resignation.action_approve_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_open_clearance_wizard()

    def test_the_cleared_label_reads_cleared(self):
        selection = dict(
            self.env['hr.resignation']._fields['clearance_state']
            ._description_selection(self.env))
        self.assertEqual(selection['done'], 'Cleared')

    # ---- CR 2.8 ------------------------------------------------------
    def test_hr_cannot_approve_before_the_manager_endorses(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_approve_resignation()

    def test_the_cycle_records_who_endorsed_and_who_approved(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        self.assertEqual(resignation.state, 'endorsed')
        self.assertEqual(resignation.endorsed_by, self.env.user)
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
        """A resignation whose last day has already passed, confirmed and
        endorsed but not yet approved -- clearance is no longer a
        precondition here, so it is left out; a caller that wants it must
        run it after approving, and only when dated for today."""
        yesterday = fields.Date.today() - timedelta(days=1)
        resignation = self._resignation(expected_revealing_date=yesterday)
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        return resignation

    def test_approving_a_past_dated_exit_archives_the_employee(self):
        """The case that could not work before.

        ellithy_hr_base refuses to archive without both exit dates and
        refuses to let an active employee hold them, so the stock approval's
        bare ``active = False`` was rejected outright.
        """
        resignation = self._approved_past_dated()
        resignation.action_approve_resignation()
        # ``_apply_employee_exit`` closes the contract before the stock
        # method runs, and the stock method only sets this on an exit whose
        # contract it still finds open -- past-dated (or today-dated) always
        # closes it first, silently leaving the click looking like it did
        # nothing.
        self.assertEqual(resignation.state, 'approved')
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

    # ---- self-service: what HR decides, not the leaver ----------------
    def test_an_employee_cannot_set_hr_only_fields_on_create(self):
        with self.assertRaises(AccessError):
            self.env['hr.resignation'].with_user(self.plain_user).create({
                'employee_id': self.plain_employee.id,
                'expected_revealing_date': '2026-12-31',
                'reason': 'Relocating.',
                'request_type': 'suspension',
            })

    def test_an_employee_created_request_defaults_to_a_plain_resignation(self):
        resignation = self.env['hr.resignation'].with_user(
            self.plain_user).create({
                'employee_id': self.plain_employee.id,
                'expected_revealing_date': '2026-12-31',
                'reason': 'Relocating.',
            })
        self.assertEqual(resignation.request_type, 'exit')
        self.assertEqual(resignation.resignation_type, 'resigned')

    def test_an_employee_cannot_blacklist_themselves_by_a_later_write(self):
        resignation = self._resignation(employee_id=self.plain_employee.id)
        with self.assertRaises(AccessError):
            resignation.with_user(self.plain_user).write({'blacklist': True})

    def test_an_employee_cannot_endorse_or_approve_their_own_exit(self):
        resignation = self._resignation(employee_id=self.plain_employee.id)
        resignation.action_confirm_resignation()
        with self.assertRaises(AccessError):
            resignation.with_user(self.plain_user).action_endorse_resignation()
        with self.assertRaises(AccessError):
            resignation.with_user(self.plain_user).action_approve_resignation()

    def test_hr_personnel_can_endorse_but_only_hr_management_approves(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.with_user(self.hr_user).action_endorse_resignation()
        self.assertEqual(resignation.state, 'endorsed')
        with self.assertRaises(AccessError):
            resignation.with_user(self.hr_user).action_approve_resignation()

    def test_the_employee_form_hides_hr_only_sections(self):
        arch = self.env['hr.resignation'].with_user(
            self.plain_user).get_view(view_type='form')['arch']
        for name in ('blacklist', 'disable_login', 'employee_contract_id',
                     'suspension_start', 'suspension_reason_id'):
            self.assertNotIn('name="%s"' % name, arch)
        self.assertNotIn('name="approvals"', arch)
        # The old free-text column is dropped from the view outright, for
        # HR too: the relation replaces it, it does not merely hide it.
        self.assertNotIn('name="employee_contract"', arch)

    def test_request_type_is_not_shown_to_anyone(self):
        """Which kind of request this is now comes from which menu it was
        raised from; a field on the form to also show or pick it would only
        be redundant, for HR as much as for the employee."""
        for user in (self.plain_user, self.hr_user):
            arch = self.env['hr.resignation'].with_user(
                user).get_view(view_type='form')['arch']
            self.assertNotIn('widget="radio"', arch)
            self.assertIn('name="request_type" invisible="1"', arch)

    def test_hr_sees_the_hr_only_sections(self):
        arch = self.env['hr.resignation'].with_user(
            self.hr_user).get_view(view_type='form')['arch']
        for name in ('blacklist', 'disable_login', 'employee_contract_id'):
            self.assertIn('name="%s"' % name, arch)

    def test_blacklist_is_hidden_for_a_suspension_not_disable_login(self):
        """Not eligible for rehire is an exit concept -- a suspension is
        coming back. ``disable_login`` is not blacklist-specific though (a
        suspension disables the login too, while it lasts), so it keeps
        its own, unrestricted group."""
        arch = self.env['hr.resignation'].with_user(
            self.hr_user).get_view(view_type='form')['arch']
        blacklist_group = re.search(
            r'<group[^>]*string="Blacklist"[^>]*>', arch)
        self.assertIsNotNone(blacklist_group)
        self.assertIn("request_type != 'exit'", blacklist_group.group())
        login_group = re.search(r'<group[^>]*string="Login"[^>]*>', arch)
        self.assertIsNotNone(login_group)
        self.assertNotIn('invisible', login_group.group())

    def test_the_suspension_menu_is_hr_only(self):
        menu = self.env.ref(
            'ellithy_ohrms_bridge.hr_resignation_menu_suspension')
        self.assertNotIn(self.env.ref('base.group_user'), menu.groups_id)
        self.assertIn(self.env.ref('ellithy_ohrms_bridge.resignation_generalist'), menu.groups_id)
        # HR management reaches it too, by implication rather than needing
        # a second group on the menu -- confirmed here since it is what
        # makes one restriction cover both roles.
        self.assertIn(self.env.ref('ellithy_ohrms_bridge.resignation_generalist'),
                       self.env.ref('ellithy_ohrms_bridge.resignation_admin').trans_implied_ids)

    # ---- withdrawing a request, and the contract relation --------------
    def test_cancelling_works_while_still_draft_or_confirmed(self):
        resignation = self._resignation()
        resignation.action_cancel_resignation()
        self.assertEqual(resignation.state, 'cancel')

        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.action_cancel_resignation()
        self.assertEqual(resignation.state, 'cancel')

    def test_cancelling_is_blocked_once_endorsed(self):
        resignation = self._resignation()
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        with self.assertRaises(ValidationError):
            resignation.action_cancel_resignation()
        self.assertEqual(resignation.state, 'endorsed')

    def test_the_contract_relation_is_filled_by_the_onchange(self):
        resignation = self.env['hr.resignation'].new({
            'employee_id': self.employee.id})
        resignation._onchange_employee_id()
        self.assertEqual(resignation.employee_contract_id, self.contract)

    def test_the_contract_is_auto_selected_on_a_plain_create(self):
        """Not only interactively: a bare ``create()`` (import, API, the
        smart button's default context) gets it too, since it is a stored
        compute rather than an onchange-only assignment."""
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'expected_revealing_date': '2026-12-31',
            'reason': 'Relocating.',
        })
        self.assertEqual(resignation.employee_contract_id, self.contract)

    def test_an_explicit_contract_is_not_overridden_by_the_compute(self):
        other = self.env['hr.contract'].create({
            'name': 'Older Contract', 'employee_id': self.employee.id,
            'wage': 2500.0, 'date_start': '2020-01-01',
            'date_end': '2022-12-31', 'state': 'close'})
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'employee_contract_id': other.id,
            'expected_revealing_date': '2026-12-31',
            'reason': 'Relocating.',
        })
        self.assertEqual(resignation.employee_contract_id, other)

    def test_the_contract_relation_is_not_lost_across_approval(self):
        """The vendor's approval loop still writes the old Char column by
        name; that must not disturb the relation shown on the form."""
        resignation = self._resignation(
            expected_revealing_date=fields.Date.today() - timedelta(days=1))
        resignation.employee_contract_id = self.contract
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        resignation.action_approve_resignation()
        self.assertEqual(resignation.employee_contract_id, self.contract)

    # ---- CR 2.7 ------------------------------------------------------
    def test_the_employee_reaches_the_resignation_by_smart_button(self):
        resignation = self._resignation()
        self.assertEqual(self.employee.resignation_count, 1)
        action = self.employee.action_view_resignations()
        self.assertEqual(action['res_model'], 'hr.resignation')
        # A single record opens straight onto its own form.
        self.assertEqual(action['res_id'], resignation.id)
