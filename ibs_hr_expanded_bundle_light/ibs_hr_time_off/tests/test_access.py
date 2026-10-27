from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'ibs_hr_time_off')
class TestTimeOffAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='timeoff_employee', groups='base.group_user')
        cls.other = new_test_user(cls.env, login='timeoff_other', groups='base.group_user')
        cls.generalist = new_test_user(cls.env, login='timeoff_generalist',
                                      groups='ibs_hr_time_off.ibs_hr_time_off_generalist')
        cls.admin = new_test_user(cls.env, login='timeoff_admin',
                                 groups='ibs_hr_time_off.ibs_hr_time_off_admin')
        cls.finance = new_test_user(cls.env, login='timeoff_finance',
                                   groups='ellithy_hr_base.group_ellithy_financial_approval')
        cls.employee = cls.user.employee_id or cls.env['hr.employee'].create({'name': 'Time Off Access Employee'})
        cls.employee.write({
            'name': 'Time Off Access Employee', 'user_id': cls.user.id,
            'joining_date': '2025-01-01', 'birthday': '1990-09-14',
            'work_email': 'employee@example.com'})
        if not cls.other.employee_id:
            cls.env['hr.employee'].create({'name': 'Other Employee', 'user_id': cls.other.id})
        cls.kind = cls.env.ref('ibs_hr_time_off.time_off_type_birthday')

    def _request(self):
        return self.env['ibs.hr.time.off.request'].with_user(self.user).create({
            'employee_id': self.employee.id, 'type_id': self.kind.id,
            'date_from': '2026-09-14', 'date_to': '2026-09-14'})

    def test_employee_scope_and_one_step_generalist(self):
        request = self._request()
        self.assertFalse(self.env['ibs.hr.time.off.request'].with_user(self.other).search([
            ('id', '=', request.id)]))
        self.assertEqual(self.env['ibs.hr.time.off.request'].with_user(self.finance).search([
            ('id', '=', request.id)]), request)
        with self.assertRaises(AccessError):
            request.with_user(self.finance).write({'reason': 'Payroll review only'})
        request.action_submit()
        with self.assertRaises(ValidationError):
            request.action_hr_approve()
        request.with_user(self.generalist).action_hr_approve()
        self.assertEqual(request.state, 'approved')

    def test_two_step_admin_gate(self):
        self.kind.approval_route = 'both'
        request = self._request()
        request.action_submit()
        request.with_user(self.generalist).action_manager_approve()
        with self.assertRaises(ValidationError):
            request.with_user(self.generalist).action_hr_approve()
        request.with_user(self.admin).action_hr_approve()
        self.assertEqual(request.state, 'approved')

    def test_import_and_context_cannot_forge_approval(self):
        request = self._request()
        with self.assertRaises(ValidationError):
            request.with_context(ibs_time_off_transition=True).write({'state': 'approved'})
        with self.assertRaises(ValidationError):
            self.env['ibs.hr.time.off.request'].with_user(self.user).create({
                'employee_id': self.employee.id, 'type_id': self.kind.id,
                'date_from': '2026-09-14', 'date_to': '2026-09-14', 'state': 'approved'})
        with self.assertRaises(AccessError):
            self.kind.with_user(self.generalist).write({'paid': False})

    def test_employee_cannot_reassign_draft(self):
        request = self._request()
        with self.assertRaises(AccessError):
            request.write({'employee_id': self.other.employee_id.id})
        self.assertEqual(request.employee_id, self.employee)

    def test_long_insured_service_accrues_thirty(self):
        self.employee.write({'joining_date': '2025-01-01',
                             'social_insurance_start_date': '2010-01-01'})
        annual = self.env.ref('ibs_hr_time_off.time_off_type_annual')
        request = self.env['ibs.hr.time.off.request'].new({
            'employee_id': self.employee.id, 'type_id': annual.id,
            'date_from': '2026-12-31', 'date_to': '2026-12-31'})
        request._ensure_entitlements(fields.Date.to_date('2026-12-31'))
        entries = self.env['ibs.hr.time.off.ledger'].search([
            ('employee_id', '=', self.employee.id), ('type_id', '=', annual.id)])
        self.assertAlmostEqual(sum(entries.mapped('amount')), 30.0)

    def test_root_and_configuration_visibility(self):
        root = self.env.ref('ibs_hr_time_off.menu_time_off_root')
        self.assertFalse(root.parent_id)
        visible = self.env['ir.ui.menu'].with_user(self.user)._visible_menu_ids()
        self.assertIn(root.id, visible)
        config = self.env.ref('ibs_hr_time_off.menu_time_off_configuration')
        self.assertNotIn(config.id, visible)
        self.assertIn(config.id, self.env['ir.ui.menu'].with_user(self.admin)._visible_menu_ids())
