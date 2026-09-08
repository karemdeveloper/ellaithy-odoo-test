from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestCommissionApproval(IbsHrCommon):
    def _record(self):
        return self.env['ibs.hr.commission.penalty'].create({
            'employee_id': self.employee.id, 'percentage': 10,
            'reason': 'Acceptance test', 'date': '2026-06-01'})

    def test_single_approval_and_execution_date(self):
        record = self._record()
        self.assertEqual(str(record.execution_date), '2026-06-01')
        record.execution_date = '2026-07-01'
        record.action_approve()
        self.assertEqual(record.approval_status, 'approved')
        self.assertEqual(record.reviewed_by, self.env.user)
        with self.assertRaises(ValidationError):
            record.action_approve()

    def test_reject_and_cancel_require_nonblank_reason(self):
        for action in ('action_reject', 'action_cancel'):
            record = self._record()
            record.rejection_reason = '  '
            with self.assertRaises(ValidationError):
                getattr(record, action)()
            record.rejection_reason = 'Incorrect charge'
            getattr(record, action)()
            self.assertIn(record.approval_status, ('rejected', 'cancel'))

    def test_hr_without_approver_group_cannot_approve_or_write_status(self):
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Commission HR author', 'login': 'commission.hr.author',
            'groups_id': [(6, 0, [self.env.ref('ellithy_hr_base.group_ellithy_hr_personnel').id])]})
        record = self._record().with_user(user)
        self.assertFalse(user.has_group('ibs_hr.group_ibs_admin_penalty_approver'))
        with self.assertRaises(ValidationError):
            record.action_approve()
        with self.assertRaises(ValidationError):
            record.write({'approval_status': 'approved'})

    def test_pending_notification_goes_to_approver(self):
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Commission approver', 'login': 'commission.approver',
            'email': 'commission.approver@example.invalid',
            'groups_id': [(6, 0, [self.env.ref('ibs_hr.group_ibs_admin_penalty_approver').id])]})
        record = self._record()
        mail = self.env['mail.mail'].search([('model', '=', record._name), ('res_id', '=', record.id)])
        self.assertEqual(len(mail), 1)
        self.assertIn(user.email, mail.email_to)
        self.assertIn('model=ibs.hr.commission.penalty', mail.body_html)
        self.assertEqual(mail.state, 'outgoing')

    def test_admin_execution_date_defaults_and_is_independent(self):
        catalog = self.env['ibs.hr.admin.penalty'].create({'name': 'Admin execution', 'cost': 10})
        record = self.env['ibs.hr.admin.penalty.record'].create({
            'employee_id': self.employee.id, 'penalty_id': catalog.id, 'date': '2026-06-01'})
        self.assertEqual(str(record.execution_date), '2026-06-01')
        record.execution_date = '2026-07-01'
        record.date = '2026-06-02'
        self.assertEqual(str(record.execution_date), '2026-07-01')
