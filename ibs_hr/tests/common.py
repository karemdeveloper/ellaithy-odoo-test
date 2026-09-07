import calendar
from datetime import date

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
            # Insurance is entered on the contract, not the employee.
            'has_social_insurance': True,
        })
        cls._setup_payroll_accounting()

    @classmethod
    def _setup_payroll_accounting(cls):
        """Give the payslip somewhere to post.

        ``hr_payroll_account_community`` is installed here, and it refuses to
        confirm a payslip whose structure has no rule carrying a debit and a
        credit account. That is a configuration prerequisite of that module,
        not of anything under test, so the fixture satisfies it rather than
        working around it.
        """
        account = cls.env['account.account']
        expense = account.search([('account_type', '=', 'expense')], limit=1)
        payable = account.search([('account_type', '=', 'liability_payable')],
                                 limit=1)
        if not (expense and payable):
            return False
        journal = cls.env['account.journal'].search(
            [('type', '=', 'general')], limit=1)
        basic = cls.env.ref('hr_payroll_community.hr_rule_basic')
        basic.write({'account_debit_id': expense.id,
                     'account_credit_id': payable.id})
        cls.structure = cls.env.ref('hr_payroll_community.structure_base')
        cls.journal = journal
        return True

    def _payslip(self, month=6, year=2026, **kwargs):
        """A standard payslip for the fixture employee.

        ``ibs.hr.payslip`` was withdrawn in 18.0.1.1.0; payroll is now
        ``hr_payroll_community``, which wants an explicit period rather than
        a year/month pair.
        """
        last_day = calendar.monthrange(year, month)[1]
        values = {
            'employee_id': self.employee.id,
            'contract_id': self.contract.id,
            'date_from': date(year, month, 1),
            'date_to': date(year, month, last_day),
        }
        if getattr(self, 'structure', None):
            values['struct_id'] = self.structure.id
        if getattr(self, 'journal', None):
            values['journal_id'] = self.journal.id
        values.update(kwargs)
        return self.env['hr.payslip'].create(values)

    def _day(self, day, month=6, year=2026, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'date': f'{year}-{month:02d}-{day:02d}',
            'state': 'present',
        }
        values.update(kwargs)
        return self.env['ibs.hr.attendance.day'].create(values)
