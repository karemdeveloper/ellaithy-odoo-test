from datetime import date, datetime, timedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'ibs_hr_shift')
class TestShiftAttendance(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Night Worker'})
        cls.shift = cls.env['ibs.hr.shift'].create({
            'name': 'Night Shift',
            'from_date': '2026-09-01',
            'to_date': '2026-09-30',
            'line_ids': [
                (0, 0, {'day': '0', 'from_time': 20.0, 'to_time': 8.0}),
                (0, 0, {'day': '1', 'is_off': True}),
            ],
        })
        cls.employee.shift_id = cls.shift

    def test_overnight_attendance_belongs_to_shift_start_date(self):
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            # Cairo is UTC+3 on these dates: 17:00/05:00 UTC is the
            # requested local 20:00/08:00 shift.
            'check_in': '2026-09-14 17:00:00',
            'check_out': '2026-09-15 05:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 14)),
        ])
        self.assertEqual(day.state, 'present')
        self.assertAlmostEqual(day.worked_hours, 12.0)
        self.assertAlmostEqual(day.scheduled_hours, 12.0)
        self.assertTrue(day.crossed_midnight)
        self.assertEqual(day.shift_from.strftime('%Y-%m-%d %H:%M:%S'),
                         '2026-09-14 17:00:00')
        self.assertEqual(day.shift_to.strftime('%Y-%m-%d %H:%M:%S'),
                         '2026-09-15 05:00:00')

    def test_off_day_is_created_without_a_punch(self):
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-15', '2026-09-15', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 15)),
        ])
        self.assertEqual(day.state, 'weekend')
        self.assertEqual(day.scheduled_hours, 0.0)

    def test_work_on_off_day_keeps_weekend_status_and_actual_hours(self):
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-09-15 07:00:00',
            'check_out': '2026-09-15 09:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-15', '2026-09-15', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 15)),
        ])
        self.assertEqual(day.state, 'weekend')
        self.assertAlmostEqual(day.worked_hours, 2.0)

    def test_absent_day_is_created_without_a_punch(self):
        self.shift.line_ids = [(0, 0, {
            'day': '2', 'from_time': 9.0, 'to_time': 17.0,
        })]
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-16', '2026-09-16', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 16)),
        ])
        self.assertEqual(day.state, 'absent')
        self.assertEqual(day.scheduled_hours, 8.0)

    def test_flexible_day_uses_entered_number_of_hours(self):
        line = self.shift.line_ids.filtered(lambda item: item.day == '0')
        line.write({
            'is_flexible': True, 'flexible_hours': 7.0,
            'from_time': 0.0, 'to_time': 0.0,
        })
        self.assertEqual(line.number_of_hours, 7.0)
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-09-14 07:00:00',
            'check_out': '2026-09-14 15:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', '2026-09-14'),
        ])
        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.early_leave_minutes, 0)
        self.assertEqual(day.overtime_hours, 1.0)

    def test_public_holiday_gets_its_own_daily_status(self):
        self.env['ibs.hr.public.holiday'].create({
            'name': 'Public Holiday',
            'date': '2026-09-14',
            'company_id': self.env.company.id,
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 14)),
        ])
        self.assertEqual(day.state, 'holiday')

    def test_each_employee_uses_their_own_shift_window(self):
        day_employee = self.env['hr.employee'].create({'name': 'Day Worker'})
        day_shift = self.env['ibs.hr.shift'].create({
            'name': 'Day Shift',
            'from_date': '2026-09-01',
            'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': '0', 'from_time': 9.0, 'to_time': 17.0,
            })],
        })
        day_employee.shift_id = day_shift
        self.env['hr.attendance'].create({
            'employee_id': day_employee.id,
            'check_in': '2026-09-14 06:00:00',
            'check_out': '2026-09-14 14:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', day_employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', day_employee.id),
            ('date', '=', date(2026, 9, 14)),
        ])
        self.assertEqual(day.shift_id, day_shift)
        self.assertEqual(day.state, 'present')
        self.assertAlmostEqual(day.scheduled_hours, 8.0)
        self.assertAlmostEqual(day.worked_hours, 8.0)

    def test_overtime_threshold_counts_complete_minutes(self):
        for minutes, seconds, expected in [
                (29, 59, 0), (30, 0, 0), (30, 59, 0),
                (30, 59.999, 0), (31, 0, 31 / 60)]:
            attendance = self.env['hr.attendance'].create({
                'employee_id': self.employee.id,
                'check_in': '2026-09-14 17:00:00',
                'check_out': datetime(2026, 9, 15, 5) + timedelta(
                    minutes=minutes, seconds=seconds)})
            values = self.env['ibs.hr.attendance.day']._attendance_values(
                self.employee, date(2026, 9, 14))
            self.assertAlmostEqual(values['overtime_hours'], expected)
            attendance.unlink()

    def test_overnight_smart_button_finds_next_day_checkout(self):
        attendance = self.env['hr.attendance'].create({
            'employee_id': self.employee.id, 'check_in': '2026-09-14 17:00:00',
            'check_out': '2026-09-15 05:00:00'})
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-15', self.employee)
        night = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-09-14')])
        off = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id), ('date', '=', '2026-09-15')])
        self.assertEqual(night.attendance_count, 1)
        self.assertEqual(off.attendance_count, 0)
        action = night.action_open_day_records('attendance')
        self.assertEqual(self.env['hr.attendance'].search(action['domain']), attendance)
