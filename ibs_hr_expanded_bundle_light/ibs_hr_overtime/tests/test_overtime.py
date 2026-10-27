from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'ibs_hr_overtime')
class TestOvertime(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'OT Employee'})
        cls.env['hr.contract'].create({
            'name': 'OT Contract', 'employee_id': cls.employee.id,
            'date_start': '2026-01-01', 'state': 'open', 'wage': 7200.0,
        })

    def _overtime(self, minutes, day, state='present'):
        attendance_day = self.env['ibs.hr.attendance.day'].create({
            'employee_id': self.employee.id,
            'date': day,
            'state': state,
            'scheduled_hours': 8.0,
            'worked_hours': minutes / 60.0 if state in ('weekend', 'holiday') else 0.0,
            'overtime_hours': minutes / 60.0,
        })
        self.env['ibs.hr.overtime'].generate_from_attendance(day, day)
        return self.env['ibs.hr.overtime'].search([
            ('attendance_day_id', '=', attendance_day.id),
        ])

    def test_thirty_minutes_is_not_payable(self):
        overtime = self._overtime(30, '2026-09-14')
        self.assertFalse(overtime)

    def test_thirty_one_minutes_pays_all_minutes(self):
        overtime = self._overtime(31, '2026-09-15')
        self.assertEqual(overtime.payable_minutes, 31)
        overtime.action_manager_approve()
        overtime.action_hr_approve()
        self.assertEqual(overtime.state, 'approved')

    def test_rest_choice_creates_one_credit(self):
        overtime = self._overtime(60, '2026-09-16', state='weekend')
        self._overtime(60, '2026-09-17', state='weekend')
        overtime.compensation = 'rest'
        overtime.action_manager_approve()
        overtime.action_hr_approve()
        self.assertEqual(overtime.rest_credit_id.state, 'available')
        self.assertEqual(overtime.rest_credit_id.days, 1.0)

    def test_rest_choice_requires_consecutive_days_off(self):
        overtime = self._overtime(60, '2026-09-18', state='weekend')
        overtime.compensation = 'rest'
        with self.assertRaises(ValidationError):
            overtime.action_manager_approve()
