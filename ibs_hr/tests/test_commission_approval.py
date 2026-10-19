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
            'groups_id': [(6, 0, [self.env.ref('ibs_hr.penalty_generalist').id])]})
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


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestCommissionPenaltyReasons(IbsHrCommon):
    """HR letter item 24: reasons are a managed list."""

    def test_a_penalty_is_recorded_against_a_listed_reason(self):
        reason = self.env.ref('ibs_hr.commission_penalty_reason_new_rating')
        before = reason.penalty_count
        record = self.env['ibs.hr.commission.penalty'].create({
            'employee_id': self.employee.id, 'percentage': 10,
            'reason_id': reason.id, 'date': '2026-06-01'})
        self.assertEqual(record.reason, 'New Rating')
        reason.invalidate_recordset()
        self.assertEqual(reason.penalty_count, before + 1)

    def test_a_code_from_the_legacy_sync_finds_its_reason(self):
        record = self.env['ibs.hr.commission.penalty'].create({
            'employee_id': self.employee.id, 'percentage': 5,
            'reason': 'average_rating', 'date': '2026-06-01'})
        self.assertEqual(record.reason_id,
                         self.env.ref('ibs_hr.commission_penalty_reason_average_rating'))

    def test_a_penalty_needs_a_reason(self):
        with self.assertRaises(ValidationError):
            self.env['ibs.hr.commission.penalty'].create({
                'employee_id': self.employee.id, 'percentage': 5,
                'date': '2026-06-01'})

    def test_penalties_report_by_reason(self):
        reason = self.env['ibs.hr.commission.penalty.reason'].create({
            'name': 'Missing Paperwork', 'default_percentage': 7.5})
        Penalty = self.env['ibs.hr.commission.penalty']
        for _i in range(2):
            Penalty.create({'employee_id': self.employee.id, 'percentage': 7.5,
                            'reason_id': reason.id, 'date': '2026-06-01'})
        groups = Penalty._read_group([('reason_id', '=', reason.id)],
                                     ['reason_id'], ['__count'])
        self.assertEqual(groups, [(reason, 2)])
