from odoo import fields
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user


@tagged('post_install', '-at_install', 'ibs_hr_permission')
class TestPermissionAccess(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = new_test_user(cls.env, login='permission_employee', groups='base.group_user')
        cls.hr = new_test_user(cls.env, login='permission_generalist',
                              groups='ibs_hr_permission.permission_generalist')
        cls.mission_hr = new_test_user(cls.env, login='mission_generalist',
                                      groups='ibs_hr_permission.mission_generalist')
        cls.employee = cls.user.employee_id or cls.env['hr.employee'].create({'name': 'Permission Access Employee'})
        cls.employee.write({
            'name': 'Permission Access Employee', 'user_id': cls.user.id})
        cls.kind = cls.env['ibs.hr.permission.type'].search([('code', '=', 'lateness')], limit=1)

    def test_permission_generalist_is_independent_of_mission(self):
        request = self.env['ibs.hr.permission'].with_user(self.user).create({
            'employee_id': self.employee.id, 'permission_type_id': self.kind.id,
            'issue_date': fields.Date.today(), 'duration_minutes': '30'})
        request.action_submit()
        with self.assertRaises(ValidationError):
            request.with_user(self.mission_hr).action_approve()
        request.with_user(self.hr).action_approve()
        self.assertEqual(request.state, 'approved')

    def test_employee_cannot_reject_or_forge_status(self):
        request = self.env['ibs.hr.permission'].with_user(self.user).create({
            'employee_id': self.employee.id, 'permission_type_id': self.kind.id,
            'issue_date': fields.Date.today(), 'duration_minutes': '30', 'reasons': 'Test'})
        request.action_submit()
        with self.assertRaises(ValidationError):
            request.action_reject()
        with self.assertRaises(ValidationError):
            request.with_context(ibs_request_transition=True).write({'state': 'approved'})

    def test_employee_menus_are_visible(self):
        visible = self.env['ir.ui.menu'].with_user(self.user)._visible_menu_ids()
        self.assertIn(self.env.ref('ibs_hr_permission.menu_ta_permissions').id, visible)
        self.assertIn(self.env.ref('ibs_hr_permission.menu_ta_missions').id, visible)

    def test_employee_cannot_reassign_draft(self):
        other = self.env['hr.employee'].create({'name': 'Another employee'})
        request = self.env['ibs.hr.permission'].with_user(self.user).create({
            'employee_id': self.employee.id, 'permission_type_id': self.kind.id,
            'issue_date': fields.Date.today(), 'duration_minutes': '30'})
        with self.assertRaises(AccessError):
            request.write({'employee_id': other.id})
