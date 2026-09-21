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

    def test_long_overnight_attendance_stays_in_checkin_day(self):
        employee = self.env['hr.employee'].create({'name': 'Long Night Worker'})
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Long Night Assignment',
            'from_date': '2026-09-01', 'to_date': '2026-09-30',
            'line_ids': [
                (0, 0, {'day': '2', 'from_time': 20.0, 'to_time': 8.0}),
                (0, 0, {'day': '3', 'from_time': 9.0, 'to_time': 17.0}),
            ],
        })
        employee.shift_id = shift
        attendance = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            # 20:00 Cairo on 9 September through 16:00 on 10 September.
            'check_in': '2026-09-09 17:00:00',
            'check_out': '2026-09-10 13:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-09', '2026-09-10', employee)
        checkin_day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-09')])
        next_day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-10')])
        self.assertEqual(checkin_day.state, 'present')
        self.assertEqual(checkin_day.check_in, attendance.check_in)
        self.assertEqual(checkin_day.check_out, attendance.check_out)
        self.assertEqual(checkin_day.worked_hours, 20.0)
        self.assertEqual(checkin_day.attendance_count, 1)
        self.assertEqual(next_day.state, 'absent')
        self.assertFalse(next_day.check_in)
        self.assertEqual(next_day.attendance_count, 0)

    def test_off_day_is_created_without_a_punch(self):
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-15', '2026-09-15', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', date(2026, 9, 15)),
        ])
        self.assertEqual(day.state, 'weekend')
        self.assertEqual(day.scheduled_hours, 0.0)

    def test_current_month_generates_running_contracts_without_punches(self):
        today = date(2029, 2, 3)
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Contract Month Shift',
            'from_date': '2029-02-01', 'to_date': '2029-02-28',
            'line_ids': [(0, 0, {
                'day': str(day), 'from_time': 9.0, 'to_time': 17.0,
            }) for day in range(7)],
        })
        scheduled = self.env['hr.employee'].create({
            'name': 'Running Scheduled Employee', 'shift_id': shift.id})
        unconfigured = self.env['hr.employee'].create({
            'name': 'Running Employee Without Shift'})
        stopped = self.env['hr.employee'].create({
            'name': 'Stopped Employee', 'shift_id': shift.id})
        self.env['hr.contract'].create([{
            'name': 'Running Scheduled Contract', 'employee_id': scheduled.id,
            'date_start': '2029-02-01', 'state': 'open', 'wage': 1000,
        }, {
            'name': 'Running Unconfigured Contract', 'employee_id': unconfigured.id,
            'date_start': '2029-02-01', 'state': 'open', 'wage': 1000,
        }, {
            'name': 'Stopped Contract', 'employee_id': stopped.id,
            'date_start': '2029-01-01', 'date_end': '2029-01-31',
            'state': 'close', 'wage': 1000,
        }])
        self.env['ibs.hr.attendance.day']._generate_current_month(
            today=today, employees=scheduled | unconfigured | stopped)
        scheduled_days = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', scheduled.id)])
        unconfigured_days = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', unconfigured.id)])
        self.assertEqual(len(scheduled_days), 3)
        self.assertEqual(len(scheduled_days.filtered(
            lambda day: day.state == 'weekend')), 1)
        self.assertEqual(len(scheduled_days.filtered(
            lambda day: day.state == 'absent')), 2)
        self.assertEqual(len(unconfigured_days), 3)
        self.assertEqual(set(unconfigured_days.mapped('state')), {'no_shift'})
        self.assertFalse(self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', stopped.id)]))

    def test_shift_without_off_day_gets_one_friday_saturday_weekend(self):
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Seven Working Days',
            'from_date': '2026-09-01', 'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': str(day), 'from_time': 9.0, 'to_time': 17.0,
            }) for day in range(7)],
        })
        employee = self.env['hr.employee'].create({
            'name': 'Automatic Weekend Worker', 'shift_id': shift.id})
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-04', '2026-09-05', employee)
        friday = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-04')])
        saturday = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-05')])
        self.assertEqual(friday.state, 'weekend')
        self.assertEqual(friday.scheduled_hours, 0.0)
        self.assertEqual(saturday.state, 'absent')
        self.assertEqual(saturday.scheduled_hours, 8.0)

    def test_automatic_weekend_moves_to_absent_saturday_if_friday_worked(self):
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Seven Days With Friday Attendance',
            'from_date': '2026-09-01', 'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': str(day), 'from_time': 9.0, 'to_time': 17.0,
            }) for day in range(7)],
        })
        employee = self.env['hr.employee'].create({
            'name': 'Saturday Weekend Worker', 'shift_id': shift.id})
        self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': '2026-09-04 06:00:00',
            'check_out': '2026-09-04 14:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-04', '2026-09-05', employee)
        friday = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-04')])
        saturday = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-09-05')])
        self.assertEqual(friday.state, 'present')
        self.assertEqual(saturday.state, 'weekend')
        self.assertEqual(saturday.scheduled_hours, 0.0)

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
        attendance = self.env['hr.attendance'].create({
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
        self.assertAlmostEqual(attendance.worked_hours, 8.0)
        self.assertEqual(attendance.overtime_hours, 0.0)
        self.assertEqual(attendance.validated_overtime_hours, 0.0)

    def test_old_open_punch_is_not_reused_by_later_days(self):
        employee = self.env['hr.employee'].create({'name': 'Open Punch Worker'})
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Open Punch Day Shift',
            'from_date': '2026-07-01', 'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': str(day), 'from_time': 9.0, 'to_time': 17.0,
            }) for day in range(7)],
        })
        employee.shift_id = shift
        old_open = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': '2026-07-16 06:00:00',
        })
        later = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': '2026-07-19 06:00:00',
            'check_out': '2026-07-19 14:00:00',
        })
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-07-16', '2026-07-19', employee)
        open_day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-07-16')])
        later_day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', employee.id), ('date', '=', '2026-07-19')])
        self.assertEqual(open_day.check_in, old_open.check_in)
        self.assertFalse(open_day.check_out)
        self.assertEqual(later_day.check_in, later.check_in)
        self.assertEqual(later_day.check_out, later.check_out)
        self.assertEqual(later_day.worked_hours, 8.0)

    def test_raw_attendance_extra_hours_use_shift_and_stay_positive(self):
        employee = self.env['hr.employee'].create({'name': 'Extra Hours Worker'})
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Positive Extra Hours Shift',
            'from_date': '2026-09-01', 'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': '0', 'from_time': 9.0, 'to_time': 17.0,
            })],
        })
        employee.shift_id = shift
        regular = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': '2026-09-14 06:00:00',
            'check_out': '2026-09-14 14:00:00',
        })
        extra = self.env['hr.attendance'].create({
            'employee_id': employee.id,
            'check_in': '2026-09-21 06:00:00',
            'check_out': '2026-09-21 14:31:00',
        })
        self.assertEqual(regular.worked_hours, 8.0)
        self.assertEqual(regular.overtime_hours, 0.0)
        self.assertEqual(regular.validated_overtime_hours, 0.0)
        self.assertAlmostEqual(extra.worked_hours, 8 + 31 / 60)
        self.assertAlmostEqual(extra.overtime_hours, 31 / 60)
        self.assertAlmostEqual(extra.validated_overtime_hours, 31 / 60)

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
