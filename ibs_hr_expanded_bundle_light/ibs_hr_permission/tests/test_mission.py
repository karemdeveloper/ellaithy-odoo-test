from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrPermissionCommon


@tagged('post_install', '-at_install', 'ibs_hr_permission')
class TestMission(IbsHrPermissionCommon):

    def _mission(self, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'issue_date': '2026-06-10',
            'destination': 'Nasr City Branch',
            'custom_hours': True,
            'start_time': 9.0,
            'end_time': 13.0,
        }
        values.update(kwargs)
        return self.env['ibs.hr.mission'].create(values)

    def _checked_in_out_mission(self, **kwargs):
        mission = self._mission(
            custom_hours=False, start_time=0.0, end_time=0.0, **kwargs)
        mission.action_check_in(latitude=30.05, longitude=31.23)
        mission.action_check_out(latitude=30.06, longitude=31.24)
        return mission

    def _complete(self, mission):
        mission.action_check_in(latitude=30.05, longitude=31.23)
        mission.action_check_out(latitude=30.06, longitude=31.24)
        return mission

    # -- duration / time span (custom hours) -----------------------------

    def test_duration_computed_from_custom_hours(self):
        self.assertAlmostEqual(self._mission().duration_hours, 4.0, places=2)

    def test_end_must_follow_start(self):
        with self.assertRaises(ValidationError):
            self._mission(start_time=13.0, end_time=9.0)

    def test_times_must_be_within_the_day(self):
        with self.assertRaises(ValidationError):
            self._mission(start_time=9.0, end_time=25.0)

    def test_time_checks_skipped_when_not_custom_hours(self):
        mission = self._mission(custom_hours=False, start_time=0.0, end_time=0.0)
        self.assertTrue(mission.id)

    def test_destination_required(self):
        with self.assertRaises(Exception):
            self._mission(destination=False)

    def test_sequence_prefix(self):
        mission = self._mission()
        self.assertTrue(mission.name.startswith('MIS/'))

    # -- check-in / check-out ---------------------------------------------

    def test_check_in_out_captures_time_and_location(self):
        mission = self._checked_in_out_mission()
        self.assertTrue(mission.checkin_time)
        self.assertEqual(mission.checkin_location, '30.050000, 31.230000')
        self.assertTrue(mission.checkout_time)
        self.assertEqual(mission.checkout_location, '30.060000, 31.240000')

    def test_duration_computed_from_check_in_out_when_not_custom_hours(self):
        mission = self._checked_in_out_mission()
        mission.checkin_time = '2026-06-10 09:00:00'
        mission.checkout_time = '2026-06-10 11:30:00'
        self.assertAlmostEqual(mission.duration_hours, 2.5, places=2)

    def test_cannot_check_out_before_check_in(self):
        mission = self._mission(custom_hours=False, start_time=0.0, end_time=0.0)
        with self.assertRaises(ValidationError):
            mission.action_check_out()

    def test_cannot_check_in_twice(self):
        mission = self._mission(custom_hours=False, start_time=0.0, end_time=0.0)
        mission.action_check_in(latitude=30.05, longitude=31.23)
        with self.assertRaises(ValidationError):
            mission.action_check_in(latitude=30.05, longitude=31.23)

    def test_submit_requires_check_in_out_when_not_custom_hours(self):
        mission = self._mission(custom_hours=False, start_time=0.0, end_time=0.0)
        with self.assertRaises(ValidationError):
            mission.action_submit()
        mission.action_check_in(latitude=30.05, longitude=31.23)
        with self.assertRaises(ValidationError):
            mission.action_submit()
        mission.action_check_out(latitude=30.06, longitude=31.24)
        mission.action_submit()
        self.assertEqual(mission.state, 'pending')

    def test_custom_hours_still_require_gps_evidence(self):
        mission = self._mission()
        with self.assertRaises(ValidationError):
            mission.action_submit()
        self._complete(mission)
        mission.action_submit()
        self.assertEqual(mission.state, 'pending')

    # -- approval workflow: manager, then HR -------------------------------

    def test_approval_flow_needs_manager_then_hr(self):
        mission = self._mission()
        self._complete(mission)
        mission.action_submit()
        self.assertEqual(mission.state, 'pending')
        mission.action_manager_approve()
        self.assertEqual(mission.state, 'manager_approved')
        mission.action_approve()
        self.assertEqual(mission.state, 'approved')

    def test_cannot_approve_from_draft(self):
        with self.assertRaises(ValidationError):
            self._mission().action_approve()

    def test_cannot_hr_approve_before_manager(self):
        mission = self._mission()
        self._complete(mission)
        mission.action_submit()
        with self.assertRaises(ValidationError):
            mission.action_approve()

    def test_manager_approve_requires_pending(self):
        with self.assertRaises(ValidationError):
            self._mission().action_manager_approve()

    def test_rejection_requires_remark(self):
        mission = self._mission()
        self._complete(mission)
        mission.action_submit()
        with self.assertRaises(ValidationError):
            mission.action_reject()
        mission.admin_remark = 'Not justified'
        mission.action_reject()
        self.assertEqual(mission.state, 'rejected')
