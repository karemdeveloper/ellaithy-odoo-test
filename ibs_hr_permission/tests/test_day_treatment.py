from datetime import timedelta

from odoo import fields
from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'ibs_hr_permission')
class TestDayTreatment(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if 'ibs.hr.shift' not in cls.env:
            return
        cls.date = fields.Date.today()
        cls.user = new_test_user(cls.env, login='day_employee', groups='base.group_user')
        cls.employee = cls.user.employee_id or cls.env['hr.employee'].create({'name': 'Day Employee'})
        cls.employee.user_id = cls.user
        cls.shift = cls.env['ibs.hr.shift'].create({
            'name': 'Day Treatment', 'from_date': cls.date,
            'to_date': cls.date + timedelta(days=10),
            'line_ids': [(0, 0, {'day': str(day), 'from_time': 9, 'to_time': 17})
                         for day in range(7)]})
        cls.employee.shift_id = cls.shift
        cls.days = cls.env['ibs.hr.attendance.day']
        cls.kind = cls.env['ibs.hr.permission.type'].search([('code', '=', 'lateness')], limit=1)

    def setUp(self):
        super().setUp()
        if 'ibs.hr.shift' not in self.env:
            self.skipTest('Shift module is optional')

    def _mission(self, start, end):
        return self.env['ibs.hr.mission'].create({
            'employee_id': self.employee.id, 'issue_date': self.date,
            'destination': 'Customer', 'custom_hours': True,
            'start_time': start, 'end_time': end, 'state': 'approved'})

    def _day(self):
        self.days.generate_days(self.date, self.date, self.employee)
        return self.days.search([
            ('employee_id', '=', self.employee.id), ('date', '=', self.date)])

    def test_mission_and_permission_cover_boundary_gap(self):
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': self.days._utc_datetime(self.date, 10),
            'check_out': self.days._utc_datetime(self.date, 17)})
        mission = self._mission(9, 9.5)
        permission = self.env['ibs.hr.permission'].create({
            'employee_id': self.employee.id, 'issue_date': self.date,
            'permission_type_id': self.kind.id, 'duration_minutes': '30',
            'state': 'approved'})
        day = self._day()
        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.mission_hours, 0.5)
        self.assertEqual(day.permission_minutes, 30)
        self.assertEqual(day.shortfall_hours, 0)
        self.assertEqual(day.mission_count, 1)
        self.assertEqual(day.permission_count, 1)
        self.assertEqual(self.env['ibs.hr.mission'].search(
            day.action_open_day_records('mission')['domain']), mission)
        self.assertEqual(self.env['ibs.hr.permission'].search(
            day.action_open_day_records('permission')['domain']), permission)
        mission.action_cancel()
        self.assertEqual(day.late_minutes, 30)
        self.assertEqual(day.mission_hours, 0)
        self.assertEqual(day.shortfall_hours, 0.5)

    def test_mission_only_day_is_present(self):
        self._mission(9, 17)
        day = self._day()
        self.assertEqual(day.state, 'present')
        self.assertEqual(day.mission_hours, 8)
        self.assertEqual(day.shortfall_hours, 0)

    def test_mission_outside_shift_does_not_cover_absence(self):
        self._mission(17, 18)
        day = self._day()
        self.assertEqual(day.state, 'absent')
        self.assertEqual(day.mission_hours, 0)

    def test_mission_overlapping_attendance_is_not_counted_twice(self):
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': self.days._utc_datetime(self.date, 10),
            'check_out': self.days._utc_datetime(self.date, 17)})
        self._mission(9, 11)
        day = self._day()
        self.assertEqual(day.mission_hours, 1)
        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.shortfall_hours, 0)

    def test_mission_covers_gap_between_separate_attendance_intervals(self):
        for start, end in [(9, 12), (13, 17)]:
            self.env['hr.attendance'].create({
                'employee_id': self.employee.id,
                'check_in': self.days._utc_datetime(self.date, start),
                'check_out': self.days._utc_datetime(self.date, end)})
        self._mission(12, 13)
        day = self._day()
        self.assertEqual(day.worked_hours, 7)
        self.assertEqual(day.mission_hours, 1)
        self.assertEqual(day.shortfall_hours, 0)
        self.assertEqual(day.attendance_count, 2)

    def test_day_buttons_enforce_ownership_and_independent_module_access(self):
        self._mission(9, 17)
        day = self._day()
        self.assertEqual(day.with_user(self.user).mission_count, 1)
        outsider = new_test_user(self.env, login='day_outsider', groups='base.group_user')
        with self.assertRaises(AccessError):
            day.with_user(outsider).action_open_day_records('mission')
        generalist = new_test_user(self.env, login='day_generalist',
                                  groups='ibs_hr_shift.ibs_hr_shift_generalist')
        self.assertEqual(day.with_user(generalist).mission_count, 0)
