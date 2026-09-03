from odoo.tests.common import TransactionCase


class IbsHrCommon(TransactionCase):
    """Shared fixture: one branch, one employee, one contract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create({
            'name': 'Sheraton HQ',
            'name_ar': 'الإدارة شيراتون',
            'company_id': cls.env.company.id,
        })
        cls.department = cls.env['hr.department'].create({
            'name': 'Finance',
            'dept_type': 'directorate',
            'branch_id': cls.branch.id,
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee',
            'name_ar': 'موظف اختبار',
            'branch_id': cls.branch.id,
            'department_id': cls.department.id,
            'has_social_insurance': True,
        })
        # 3,000 basic gives a clean daily rate of 100.00 on the /30 basis,
        # which keeps the arithmetic in these tests readable.
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Test Contract',
            'employee_id': cls.employee.id,
            'wage': 3000.0,
            'subscription_wage': 2000.0,
            'transportation_allowance': 200.0,
            'date_start': '2026-01-01',
            'state': 'open',
        })

    def _payslip(self, month=6, year=2026, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'salary_year': year,
            'salary_month': month,
        }
        values.update(kwargs)
        return self.env['ibs.hr.payslip'].create(values)

    def _day(self, day, month=6, year=2026, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'date': f'{year}-{month:02d}-{day:02d}',
            'state': 'present',
        }
        values.update(kwargs)
        return self.env['ibs.hr.attendance.day'].create(values)
