from odoo.tests import tagged
from odoo.exceptions import ValidationError
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'ibs_hr_payroll')
class TestHcmPayroll(TransactionCase):

    def test_optional_input_without_line_is_zero(self):
        basic = self.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
        rule = self.env['hr.salary.rule'].create({
            'name': 'Optional input test', 'code': 'OPTIONAL_ZERO',
            'category_id': basic.category_id.id, 'sequence': 50,
            'condition_select': 'none', 'amount_select': 'code',
            'amount_python_compute': 'result = inputs.MISSING_OPTIONAL.amount',
        })
        self.contract.struct_id.rule_ids = [(4, rule.id)]
        self.payslip.action_compute_sheet()
        lines = self.payslip.line_ids.filtered(lambda line: line.code == 'OPTIONAL_ZERO')
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines.total, 0.0)

    def test_finance_finalizes_but_cannot_edit_details(self):
        finance = new_test_user(self.env, login='hcm_payroll_finance',
                                groups='ibs_hr_payroll.ibs_hr_payroll_finance')
        generalist = new_test_user(self.env, login='hcm_payroll_generalist',
                                   groups='ibs_hr_payroll.ibs_hr_payroll_generalist')
        self.payslip.with_user(generalist).action_compute_sheet()
        with self.assertRaises(ValidationError):
            self.payslip.with_user(generalist).action_payslip_done()
        with self.assertRaises(ValidationError):
            self.payslip.with_user(finance).with_context(hcm_workflow=True).write({'state': 'done'})
        with self.assertRaises(ValidationError):
            self.payslip.line_ids[:1].with_user(finance).write({'amount': 1})
        self.payslip.with_user(finance).action_payslip_done()
        self.assertEqual(self.payslip.state, 'done')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({'name': 'Payroll Employee'})
        cls.contract = cls.env['hr.contract'].create({
            'name': 'Payroll Contract',
            'employee_id': cls.employee.id,
            'date_start': '2026-01-01',
            'state': 'open',
            'wage': 9000.0,
            'transportation_allowance_daily': 50.0,
            'employment_allowance': 500.0,
            'commitment_allowance': 300.0,
            'other_allowance': 200.0,
            'subscription_wage': 8000.0,
            'has_social_insurance': True,
            'social_insurance_percentage': 11.25,
            'mobile_invoice_deduction': 100.0,
            'struct_id': cls.env.ref(
                'hr_payroll_community.structure_base').id,
        })
        payslip_values = {
            'employee_id': cls.employee.id,
            'contract_id': cls.contract.id,
            'date_from': '2026-09-01',
            'date_to': '2026-09-30',
            'struct_id': cls.contract.struct_id.id,
        }
        if 'journal_id' in cls.env['hr.payslip']._fields:
            journal = cls.env['account.journal'].create({
                'name': 'HCM Payroll Test', 'code': 'HCP', 'type': 'general',
                'company_id': cls.env.company.id})
            payslip_values['journal_id'] = journal.id
            expense = cls.env['account.account'].create({
                'name': 'Test Salary Expense', 'code': 'HCMEXP',
                'account_type': 'expense', 'company_ids': [(4, cls.env.company.id)]})
            payable = cls.env['account.account'].create({
                'name': 'Test Salary Liability', 'code': 'HCMPAY',
                'account_type': 'liability_current', 'company_ids': [(4, cls.env.company.id)]})
            basic = cls.env['hr.salary.rule'].search([('code', '=', 'BASIC')], limit=1)
            basic.write({'account_debit_id': expense.id, 'account_credit_id': payable.id})

        cls.payslip = cls.env['hr.payslip'].create(payslip_values)

    def test_contract_insurance_is_eleven_point_two_five_percent(self):
        self.assertEqual(self.contract.social_insurance_amount, 900.0)

    def test_all_hcm_amounts_are_mapped(self):
        self.env['ibs.hr.attendance.day'].create({
            'employee_id': self.employee.id,
            'date': '2026-09-14',
            'state': 'present',
            'check_in': '2026-09-14 06:00:00',
            'check_out': '2026-09-14 14:00:00',
            'scheduled_hours': 8.0,
        })
        mobile = self.env['ibs.hr.mobile.deduction'].create({
            'employee_id': self.employee.id,
            'period': '2026-09-01',
            'reference': 'INV-SEP',
            'amount': 150.0,
        })
        mobile.action_approve()
        amounts = self.payslip._hcm_amounts()
        self.assertEqual(amounts['TRANSPORT'], 50.0)
        self.assertEqual(amounts['EMPLOYMENT'], 500.0)
        self.assertEqual(amounts['COMMITMENT'], 300.0)
        self.assertEqual(amounts['OTHER_ALLOW'], 200.0)
        self.assertEqual(amounts['SOC_INS'], 900.0)
        self.assertEqual(amounts['MOBILE'], 150.0)

    def test_salary_rules_post_sources_once_and_reset_releases_them(self):
        self.env['ibs.hr.attendance.day'].create({
            'employee_id': self.employee.id,
            'date': '2026-09-14',
            'state': 'present',
            'check_in': '2026-09-14 06:00:00',
            'check_out': '2026-09-14 14:00:00',
            'scheduled_hours': 8.0,
        })
        inputs = self.payslip.get_inputs(
            self.contract, self.payslip.date_from, self.payslip.date_to)
        self.payslip.input_line_ids = [(0, 0, values) for values in inputs]
        self.payslip.action_payslip_done()
        self.assertEqual(self.payslip.state, 'done')
        self.assertEqual(self.payslip.get_salary_line_total('TRANSPORT'), 50.0)
        self.assertEqual(self.payslip.get_salary_line_total('EMPLOYMENT'), 500.0)
        self.assertEqual(self.payslip.get_salary_line_total('COMMITMENT'), 300.0)
        self.assertEqual(self.payslip.get_salary_line_total('OTHER_ALLOW'), 200.0)
        self.assertEqual(self.payslip.get_salary_line_total('SOC_INS'), -900.0)
        self.assertEqual(self.payslip.get_salary_line_total('MOBILE'), -100.0)
        self.assertTrue(self.payslip.hcm_source_ids)

        source_count = len(self.payslip.hcm_source_ids)
        self.payslip.action_payslip_draft()
        self.assertFalse(self.payslip.hcm_source_ids)
        self.payslip.action_payslip_done()
        self.assertEqual(len(self.payslip.hcm_source_ids), source_count)
        self.payslip.action_payslip_done()
        self.assertEqual(len(self.payslip.hcm_source_ids), source_count)

    def test_mission_overlap_is_covered_once(self):
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Mission Shift',
            'from_date': '2026-09-01',
            'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': '0', 'from_time': 9.0, 'to_time': 17.0,
            })],
        })
        self.employee.shift_id = shift
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-09-14 07:00:00',
            'check_out': '2026-09-14 08:00:00',
        })
        mission = self.env['ibs.hr.mission'].create({
            'employee_id': self.employee.id,
            'issue_date': '2026-09-14',
            'destination': 'Customer',
            'custom_hours': True,
            'start_time': 10.0,
            'end_time': 12.0,
        })
        mission.action_check_in(latitude=30.05, longitude=31.23)
        mission.action_check_out(latitude=30.06, longitude=31.24)
        mission.action_submit()
        mission.action_manager_approve()
        mission.action_approve()
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', '2026-09-14'),
        ])
        self.assertEqual(day.worked_hours, 1.0)
        self.assertEqual(day.mission_hours, 1.0)
        self.assertEqual(day.shortfall_hours, 6.0)

    def test_lateness_permission_covers_only_actual_lateness(self):
        shift = self.env['ibs.hr.shift'].create({
            'name': 'Permission Shift',
            'from_date': '2026-09-01',
            'to_date': '2026-09-30',
            'line_ids': [(0, 0, {
                'day': '0', 'from_time': 9.0, 'to_time': 17.0,
            })],
        })
        self.employee.shift_id = shift
        self.env['hr.attendance'].create({
            'employee_id': self.employee.id,
            'check_in': '2026-09-14 07:00:00',
            'check_out': '2026-09-14 14:00:00',
        })
        permission = self.env['ibs.hr.permission'].create({
            'employee_id': self.employee.id,
            'permission_type_id': self.env.ref(
                'ibs_hr_permission.permission_type_lateness').id,
            'issue_date': '2026-09-14',
            'duration_minutes': '60',
        })
        permission.action_submit()
        permission.action_approve()
        self.env['ibs.hr.attendance.day'].generate_days(
            '2026-09-14', '2026-09-14', self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', '2026-09-14'),
        ])
        self.assertEqual(day.late_minutes, 0)
        self.assertEqual(day.permission_minutes, 60)
        self.assertEqual(day.shortfall_hours, 0.0)
