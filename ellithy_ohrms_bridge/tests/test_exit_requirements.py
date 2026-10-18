from datetime import timedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestExitRequirements(EllithyBridgeCommon):
    """HR letter items 11, 20 and leaving reasons (recruitment 12)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.manager = cls.env['hr.employee'].create({
            'name': 'Direct Manager', 'branch_id': cls.branch.id,
            'work_email': 'manager@example.com'})
        cls.employee.parent_id = cls.manager
        cls.dept_finance.write({'clearance_default': True,
                                'manager_id': cls.manager.id})
        cls.reason = cls.env.ref('ellithy_ohrms_bridge.departure_reason_better_offer')

    def _exit(self, last_day=None, reason=True):
        values = {
            'employee_id': self.employee.id,
            'expected_revealing_date': last_day or fields.Date.today(),
            'reason': 'Better offer.',
            'resignation_type': 'resigned',
        }
        if reason:
            values['departure_reason_id'] = self.reason.id
        resignation = self.env['hr.resignation'].create(values)
        resignation.action_confirm_resignation()
        resignation.action_endorse_resignation()
        return resignation

    def test_an_exit_needs_a_leaving_reason_before_approval(self):
        resignation = self._exit(reason=False)
        with self.assertRaises(ValidationError):
            resignation.action_approve_resignation()

    def test_the_leaving_reason_is_written_on_the_employee(self):
        resignation = self._exit()
        resignation.action_approve_resignation()
        self.employee.invalidate_recordset()
        self.assertFalse(self.employee.active)
        self.assertEqual(self.employee.departure_reason_id, self.reason)

    def test_clearance_includes_the_direct_manager_and_default_departments(self):
        resignation = self._exit()
        resignation.action_approve_resignation()
        wizard = self.env['hr.resignation.clearance.wizard'].create({
            'resignation_id': resignation.id})
        self.assertIn(self.dept_finance, wizard.department_ids)
        self.assertTrue(wizard.include_direct_manager)
        wizard.action_start_clearance()
        lines = resignation.clearance_line_ids
        manager_line = lines.filtered(lambda l: l.line_type == 'manager')
        self.assertEqual(manager_line.manager_id, self.manager)
        self.assertIn(self.dept_finance, lines.department_id)
        # Every signer is asked at once.
        mails = self.env['mail.mail'].search([
            ('model', '=', 'hr.resignation'), ('res_id', '=', resignation.id),
            ('email_to', '=', 'manager@example.com')])
        self.assertEqual(len(mails), 2, 'one mail per line the manager signs')

    def test_a_future_exit_is_announced_on_the_employee(self):
        # The approved last day is the confirmation date plus the contract's
        # notice period; that is the day the daily job archives the leaver.
        self.contract.notice_days = 10
        last_day = fields.Date.today() + timedelta(days=10)
        resignation = self._exit(last_day=last_day)
        resignation.action_approve_resignation()
        self.employee.invalidate_recordset()
        self.assertTrue(self.employee.active)
        self.assertEqual(self.employee.scheduled_exit_date,
                         resignation.approved_revealing_date)
        self.assertEqual(self.employee.scheduled_exit_date, last_day)
