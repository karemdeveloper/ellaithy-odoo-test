from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSuspensionAndBlacklist(EllithyBridgeCommon):
    """Suspension and blacklisting, folded into hr.resignation.

    They used to live in a separate wizard on the employee form, which could
    archive someone without leaving a record anyone could review.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.reason = cls.env['ellithy.hr.suspension.reason'].create(
            {'name': 'Pending investigation'})

    _UNSET = object()

    def _suspension(self, start=_UNSET, end=None, **kwargs):
        # ``start`` uses a sentinel rather than a None default: False is a
        # value the tests below pass deliberately, and `start or today` would
        # quietly turn it back into today.
        values = {
            'employee_id': self.employee.id,
            'request_type': 'suspension',
            'reason': 'Under investigation.',
            'suspension_start': (
                fields.Date.today() if start is self._UNSET else start),
            'suspension_end': end,
            'suspension_reason_id': self.reason.id,
        }
        values.update(kwargs)
        return self.env['hr.resignation'].create(values)

    def _approve(self, resignation):
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        resignation.action_approve_resignation()
        return resignation

    # ---- shape --------------------------------------------------------
    def test_a_suspension_needs_a_start_date(self):
        with self.assertRaises(ValidationError):
            self._suspension(start=False)

    def test_a_suspension_cannot_end_before_it_starts(self):
        today = fields.Date.today()
        with self.assertRaises(ValidationError):
            self._suspension(start=today, end=today - timedelta(days=5))

    def test_the_last_day_is_filled_from_the_suspension_start(self):
        """The stock field is required, and asking for the same date twice
        is how it gets filled in wrong."""
        start = fields.Date.today() - timedelta(days=2)
        suspension = self._suspension(start=start)
        self.assertEqual(suspension.expected_revealing_date, start)

    def test_a_suspension_needs_no_clearance(self):
        """Clearance is about handing property back on the way out."""
        suspension = self._suspension(
            start=fields.Date.today() - timedelta(days=1))
        suspension.action_confirm_resignation()
        self.assertFalse(suspension.clearance_line_ids)
        suspension.action_endorse_resignation()
        suspension.action_approve_resignation()
        self.assertEqual(suspension.state, 'approved')

    # ---- effect -------------------------------------------------------
    def test_approving_suspends_the_employee(self):
        suspension = self._approve(self._suspension(
            start=fields.Date.today() - timedelta(days=1)))
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)
        self.assertEqual(self.employee.inactive_type, 'suspension')
        self.assertEqual(self.employee.suspension_reason_id, self.reason)
        # A suspension is not a departure.
        self.assertFalse(self.employee.resignation_type)
        self.assertFalse(self.employee.resigned)
        self.assertFalse(self.employee.fired)
        self.assertFalse(self.employee.departure_reason_id)
        self.assertEqual(suspension.state, 'approved')

    def test_a_future_suspension_leaves_the_employee_working(self):
        self._approve(self._suspension(
            start=fields.Date.today() + timedelta(days=7)))
        self.assertTrue(self.employee.active)

    def test_the_cron_reinstates_once_the_suspension_ends(self):
        today = fields.Date.today()
        suspension = self._approve(self._suspension(
            start=today - timedelta(days=10), end=today - timedelta(days=1)))
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)

        self.env['hr.resignation'].update_employee_status()
        self.employee.invalidate_recordset()
        self.assertTrue(self.employee.active)
        # The legacy rule forbids an active employee holding exit dates.
        self.assertFalse(self.employee.last_working_day)
        self.assertFalse(self.employee.inactive_type)
        self.assertEqual(suspension.state, 'approved')

    def test_an_open_ended_suspension_is_not_lifted_automatically(self):
        suspension = self._approve(self._suspension(
            start=fields.Date.today() - timedelta(days=10), end=False))
        self.env['hr.resignation'].update_employee_status()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)
        self.assertEqual(suspension.request_type, 'suspension')

    def test_a_suspended_employee_can_still_be_given_an_exit(self):
        """The stock model blocks any second request outright."""
        self._approve(self._suspension(
            start=fields.Date.today() - timedelta(days=1)))
        exit_request = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'reason': 'Did not return.',
            'resignation_type': 'fired',
            'expected_revealing_date': fields.Date.today(),
        })
        self.assertTrue(exit_request.id)

    def test_two_requests_cannot_be_in_flight_at_once(self):
        first = self._suspension(start=fields.Date.today())
        first.action_confirm_resignation()
        with self.assertRaises(ValidationError):
            self.env['hr.resignation'].create({
                'employee_id': self.employee.id,
                'reason': 'Also leaving.',
                'resignation_type': 'resigned',
                'expected_revealing_date': fields.Date.today(),
            })

    # ---- blacklist ----------------------------------------------------
    def test_blacklisting_requires_a_reason(self):
        with self.assertRaises(ValidationError):
            self._suspension(start=fields.Date.today(), blacklist=True)

    def test_blacklist_reaches_the_employee_on_approval(self):
        self._approve(self._suspension(
            start=fields.Date.today() - timedelta(days=1),
            blacklist=True,
            blacklist_reason='Gross misconduct.'))
        self.employee.invalidate_recordset()
        self.assertTrue(self.employee.blacklist)
        self.assertEqual(self.employee.blacklist_reason, 'Gross misconduct.')

    def test_blacklist_works_on_an_exit_too(self):
        resignation = self.env['hr.resignation'].create({
            'employee_id': self.employee.id,
            'reason': 'Dismissed.',
            'resignation_type': 'fired',
            'expected_revealing_date': fields.Date.today() - timedelta(days=1),
            'blacklist': True,
            'blacklist_reason': 'Theft.',
            'departure_reason_id': self.env.ref('hr.departure_fired').id,
        })
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        resignation.action_approve_resignation()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)
        self.assertTrue(self.employee.blacklist)

    # ---- the wizard is gone -------------------------------------------
    def test_the_status_wizard_no_longer_exists(self):
        self.assertNotIn(
            'ellithy.hr.employee.status.wizard', self.env)
        self.assertFalse(hasattr(
            self.env['hr.employee'], 'action_open_status_wizard'))
