from odoo.tests.common import TransactionCase


class IbsHrPermissionCommon(TransactionCase):
    """Shared fixture: one branch, one department, one employee.

    Deliberately lighter than ``ibs_hr``'s fixture (no contract, no payroll
    accounting setup) -- this addon has no payroll dependency to satisfy.
    """

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
        })
