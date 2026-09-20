from odoo.tests import TransactionCase


class EllithyBridgeCommon(TransactionCase):
    """One branch, one employee with three years of service, one contract.

    3,000 basic gives a clean daily rate of 100 on the /30 basis and a loan
    ceiling of exactly 6,000, which keeps the arithmetic in these tests
    readable.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create({
            'name': 'Bridge HQ', 'company_id': cls.env.company.id})
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Loan Applicant',
            'branch_id': cls.branch.id,
            'joining_date': '2023-01-01',
        })
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Bridge Contract',
            'employee_id': cls.employee.id,
            'wage': 3000.0,
            'date_start': '2023-01-01',
            'state': 'open',
        })
        cls.hr_user = cls.env['res.users'].create({
            'name': 'HR Officer',
            'login': 'bridge.hr.officer',
            'groups_id': [(4, cls.env.ref(
                'ellithy_hr_base.group_ellithy_hr_generalist').id)],
        })
        cls.dept_it = cls.env['hr.department'].create({'name': 'IT'})
        cls.dept_finance = cls.env['hr.department'].create({'name': 'Finance'})
        cls.plain_user = cls.env['res.users'].create({
            'name': 'Ordinary Employee',
            'login': 'bridge.plain.user',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        # ``oh_employee_creation_from_user`` auto-creates a matching
        # employee for every new user, so this is the one to use for a
        # "the leaver themselves" test -- ``cls.employee`` cannot also be
        # pointed at this user without violating hr_employee_user_uniq.
        cls.plain_employee = cls.plain_user.employee_id
        cls.plain_employee.joining_date = '2023-01-01'
        # The vendor's own approval step requires a contract to exist at
        # all, regardless of clearance.
        cls.plain_contract = cls.env['hr.contract'].create({
            'name': 'Plain Employee Contract',
            'employee_id': cls.plain_employee.id,
            'wage': 3000.0,
            'date_start': '2023-01-01',
            'state': 'open',
        })
