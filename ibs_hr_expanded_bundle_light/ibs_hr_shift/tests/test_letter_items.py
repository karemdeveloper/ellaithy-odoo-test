import base64
import io
from datetime import date

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'ibs_hr_shift')
class TestShiftLetterItems(TransactionCase):
    """HR letter items 15, 16 and 19, and the company default shift."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shift = cls.env['ibs.hr.shift'].create({
            'name': 'Office 09-17', 'from_date': '2026-01-01', 'to_date': '2026-12-31',
            'default_from_time': 9.0, 'default_to_time': 17.0, 'rest_day': '4',
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Punch Tester', 'employee_code': 'PT-7781'})

    # ---- item 15 -----------------------------------------------------
    def test_a_new_shift_starts_with_the_whole_week(self):
        lines = self.shift.line_ids
        self.assertEqual(len(lines), 7)
        friday = lines.filtered(lambda l: l.day == '4')
        self.assertTrue(friday.is_off)
        monday = lines.filtered(lambda l: l.day == '0')
        self.assertEqual((monday.from_time, monday.to_time), (9.0, 17.0))
        self.assertEqual(monday.number_of_hours, 8.0)

    def test_apply_to_all_days_rewrites_the_week_with_two_rest_days(self):
        self.shift.write({'default_from_time': 10.0, 'default_to_time': 18.0,
                          'second_rest_day': '5'})
        self.shift.action_generate_week()
        lines = self.shift.line_ids
        self.assertEqual(len(lines), 7)
        self.assertEqual(set(lines.filtered('is_off').mapped('day')), {'4', '5'})
        self.assertEqual(set(lines.filtered(lambda l: not l.is_off).mapped('from_time')), {10.0})

    def test_a_day_can_still_be_edited(self):
        thursday = self.shift.line_ids.filtered(lambda l: l.day == '3')
        thursday.to_time = 14.0
        self.assertEqual(thursday.number_of_hours, 5.0)

    # ---- item 16 -----------------------------------------------------
    def test_many_employees_are_assigned_at_once(self):
        others = self.env['hr.employee'].create([{'name': 'Bulk %s' % i} for i in range(3)])
        wizard = self.env['ibs.hr.shift.assign.wizard'].with_context(
            active_model='hr.employee', active_ids=others.ids).create({
                'shift_id': self.shift.id, 'regenerate': False})
        self.assertEqual(wizard.employee_ids, others)
        wizard.action_assign()
        self.assertEqual(set(others.mapped('shift_id')), {self.shift})
        self.assertEqual(self.shift.employee_count, 3)

    def test_assignment_can_skip_employees_who_have_a_shift(self):
        other_shift = self.shift.copy({'name': 'Other'})
        kept = self.env['hr.employee'].create({'name': 'Kept', 'shift_id': other_shift.id})
        free = self.env['hr.employee'].create({'name': 'Free'})
        self.env['ibs.hr.shift.assign.wizard'].create({
            'shift_id': self.shift.id, 'employee_ids': [(6, 0, (kept | free).ids)],
            'only_without_shift': True, 'regenerate': False}).action_assign()
        self.assertEqual(kept.shift_id, other_shift)
        self.assertEqual(free.shift_id, self.shift)

    # ---- company default shift ----------------------------------------
    def test_the_company_default_applies_to_employees_without_a_shift(self):
        self.env.company.ibs_default_shift_id = self.shift
        self.assertEqual(self.employee.effective_shift_id, self.shift)
        Day = self.env['ibs.hr.attendance.day']
        Day.generate_days('2026-10-12', '2026-10-12', self.employee)  # a Monday
        day = Day.search([('employee_id', '=', self.employee.id),
                          ('date', '=', date(2026, 10, 12))])
        self.assertEqual(day.state, 'absent')
        self.assertEqual(day.shift_id, self.shift)

    def test_without_any_shift_the_day_is_still_no_shift(self):
        self.env.company.ibs_default_shift_id = False
        Day = self.env['ibs.hr.attendance.day']
        Day.generate_days('2026-10-12', '2026-10-12', self.employee)
        day = Day.search([('employee_id', '=', self.employee.id),
                          ('date', '=', date(2026, 10, 12))])
        self.assertEqual(day.state, 'no_shift')

    # ---- item 19 -----------------------------------------------------
    def _upload(self, rows, name='punches.csv', **kw):
        content = '\n'.join(','.join(row) for row in rows).encode()
        wizard = self.env['ibs.hr.punch.import.wizard'].create(dict({
            'file': base64.b64encode(content), 'filename': name}, **kw))
        wizard.action_import()
        return wizard

    def test_punches_are_paired_into_one_attendance_per_day(self):
        self.employee.shift_id = self.shift
        wizard = self._upload([
            ('AC-No.', 'Date Time'),
            ('PT-7781', '2026-10-12 08:55:00'),
            ('PT-7781', '2026-10-12 13:01:00'),
            ('PT-7781', '2026-10-12 17:10:00'),
            ('PT-7781', '2026-10-13 09:20:00'),
            ('UNKNOWN', '2026-10-13 09:20:00'),
        ])
        attendances = self.env['hr.attendance'].search(
            [('employee_id', '=', self.employee.id)], order='check_in')
        self.assertEqual(len(attendances), 2)
        # Cairo is UTC+3 in October 2026.
        self.assertEqual(str(attendances[0].check_in), '2026-10-12 05:55:00')
        self.assertEqual(str(attendances[0].check_out), '2026-10-12 14:10:00')
        self.assertIn('UNKNOWN', wizard.result)
        days = self.env['ibs.hr.attendance.day'].search(
            [('employee_id', '=', self.employee.id)], order='date')
        monday, tuesday = days
        self.assertEqual(monday.state, 'present')
        self.assertFalse(monday.single_punch)
        self.assertTrue(tuesday.single_punch, 'one punch is a single fingerprint')
        self.assertEqual(tuesday.late_minutes, 20)

    def test_separate_date_and_time_columns_and_numeric_codes(self):
        employee = self.env['hr.employee'].create({'name': 'Numeric', 'barcode': '4512'})
        self._upload([('User ID', 'Date', 'Time'),
                      ('4512', '12/10/2026', '09:00'), ('4512', '12/10/2026', '17:00')],
                     match_by='barcode')
        attendance = self.env['hr.attendance'].search([('employee_id', '=', employee.id)])
        self.assertEqual(len(attendance), 1)
        self.assertEqual(str(attendance.check_in), '2026-10-12 06:00:00')
        self.assertEqual(str(attendance.check_out), '2026-10-12 14:00:00')

    def test_a_device_export_with_date_time_under_time(self):
        self._upload([('AC-No.', 'Name', 'Time', 'State'),
                      ('PT-7781', 'Punch Tester', '15/10/2026 09:00:00', 'C/In'),
                      ('PT-7781', 'Punch Tester', '15/10/2026 17:00:00', 'C/Out')])
        attendance = self.env['hr.attendance'].search([('employee_id', '=', self.employee.id)])
        self.assertEqual(str(attendance.check_in), '2026-10-15 06:00:00')

    def test_an_existing_day_is_not_touched(self):
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-10-12 06:00:00', 'check_out': '2026-10-12 14:00:00'})
        wizard = self._upload([('Employee Code', 'Date Time'),
                               ('PT-7781', '2026-10-12 08:00:00')])
        self.assertEqual(self.env['hr.attendance'].search_count(
            [('employee_id', '=', self.employee.id)]), 1)
        self.assertIn('already on file: 1', wizard.result)

    def test_xlsx_upload(self):
        import openpyxl
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(['Employee Code', 'Date Time'])
        sheet.append(['PT-7781', '2026-10-14 09:00:00'])
        sheet.append(['PT-7781', '2026-10-14 17:00:00'])
        buffer = io.BytesIO()
        book.save(buffer)
        wizard = self.env['ibs.hr.punch.import.wizard'].create({
            'file': base64.b64encode(buffer.getvalue()), 'filename': 'export.xlsx'})
        wizard.action_import()
        self.assertEqual(self.env['hr.attendance'].search_count(
            [('employee_id', '=', self.employee.id)]), 1)
