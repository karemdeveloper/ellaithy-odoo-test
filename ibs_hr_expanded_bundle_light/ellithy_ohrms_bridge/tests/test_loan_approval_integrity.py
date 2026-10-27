from datetime import date
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import EllithyBridgeCommon


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestLoanApprovalIntegrity(EllithyBridgeCommon):
    def _loan(self, **kwargs):
        vals = {'employee_id': self.employee.id, 'loan_amount': 3000,
                'installment': 3, 'payment_date': '2026-06-01'}
        vals.update(kwargs)
        if not vals.get('employee_account_id'):
            account = self.env['account.account'].search([
                ('account_type', '=', 'asset_current'), ('company_ids', 'in', self.env.company.id)], limit=1)
            if not account:
                account = self.env['account.account'].create({
                    'name': 'Test Employee Loan', 'code': 'HCMLOAN',
                    'account_type': 'asset_current', 'company_ids': [(4, self.env.company.id)]})
            treasury = self.env['account.account'].search([('code', '=', 'HCMTREAS'), ('company_ids', 'in', self.env.company.id)], limit=1)
            treasury = treasury or self.env['account.account'].create({
                'name': 'Test Treasury', 'code': 'HCMTREAS',
                'account_type': 'asset_cash', 'company_ids': [(4, self.env.company.id)]})
            journal = self.env['account.journal'].search([('code', '=', 'HCL'), ('company_id', '=', self.env.company.id)], limit=1)
            journal = journal or self.env['account.journal'].create({
                'name': 'Test Loan Journal', 'code': 'HCL', 'type': 'general',
                'company_id': self.env.company.id})
            vals.update(employee_account_id=account.id, treasury_account_id=treasury.id, journal_id=journal.id)

        return self.env['hr.loan'].create(vals)

    def _finance(self):
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Loan Finance', 'login': 'loan.finance.integrity',
            'email': 'finance@example.invalid',
            'groups_id': [(6, 0, [self.env.ref('ellithy_ohrms_bridge.loan_finance').id])]})

    def test_changed_amount_is_blocked_after_submission(self):
        """Terms lock the moment the request leaves draft -- there is no
        window left, between submission and HR's decision, for the amount
        to be changed and only caught later at approval."""
        loan = self._loan()
        loan.action_submit()
        with self.assertRaises(ValidationError):
            loan.loan_amount = 6000.01

    def test_actual_schedule_outside_year_rejected(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_compute_installment()
        loan.loan_lines[-1].date = '2027-01-01'
        with self.assertRaises(ValidationError):
            loan.action_approve()

    def test_schedule_amounts_must_equal_principal(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_compute_installment()
        loan.loan_lines[0].amount = 1
        with self.assertRaises(ValidationError):
            loan.action_approve()

    def test_finance_cannot_take_hr_step_even_with_existing_lines(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_compute_installment()
        finance = self._finance()
        self.assertFalse(finance.has_group('ellithy_hr_base.group_ellithy_hr_generalist'))
        with self.assertRaises(ValidationError):
            loan.with_user(finance).action_approve()
        with self.assertRaises(ValidationError):
            loan.with_user(finance).write({'state': 'waiting_approval_2'})

    def test_hr_cannot_take_finance_step(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_approve()
        self.assertFalse(self.hr_user.has_group('ellithy_ohrms_bridge.loan_finance'))
        with self.assertRaises(ValidationError):
            loan.with_user(self.hr_user).action_double_approve()

    def test_approved_terms_and_lines_cannot_be_changed(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_approve()
        with self.assertRaises(ValidationError):
            loan.loan_amount = 4000
        with self.assertRaises(ValidationError):
            loan.loan_lines[0].date = '2027-01-01'
        with self.assertRaises(ValidationError):
            loan.loan_lines[0].unlink()

    def test_every_term_is_blocked_once_submitted(self):
        """Not just the amount: every term the requester could otherwise
        tune after the fact, once there is nothing left to do but wait for
        HR or cancel."""
        loan = self._loan()
        loan.action_submit()
        other_employee = self.env['hr.employee'].create({'name': 'Someone Else'})
        for vals in (
            {'employee_id': other_employee.id},
            {'installment': 5},
            {'payment_date': '2026-07-01'},
            {'currency_id': self.env.ref('base.USD').id},
            {'loan_lines': [(5, 0, 0)]},
        ):
            with self.assertRaises(ValidationError):
                loan.write(vals)

    def test_compute_installment_still_works_through_hr_approval(self):
        """The form's button and inline edits are blocked once submitted,
        but ``action_approve``'s own auto-compute for a request that never
        had its schedule computed in draft does not go through this guard
        -- it must keep working regardless."""
        loan = self._loan()
        loan.action_submit()
        self.assertFalse(loan.loan_lines)
        loan.action_approve()
        self.assertEqual(len(loan.loan_lines), loan.installment)

    def test_cancelling_works_while_still_draft_or_submitted(self):
        loan = self._loan()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancel')

        loan = self._loan()
        loan.action_submit()
        loan.action_cancel()
        self.assertEqual(loan.state, 'cancel')

    def test_cancelling_is_blocked_once_hr_approves(self):
        loan = self._loan()
        loan.action_submit()
        loan.action_approve()
        with self.assertRaises(ValidationError):
            loan.action_cancel()
        self.assertEqual(loan.state, 'waiting_approval_2')

    def test_each_handoff_queues_one_email_for_the_right_group(self):
        self.hr_user.email = 'hr@example.invalid'
        finance = self._finance()
        loan = self._loan()
        domain = [('model', '=', 'hr.loan'), ('res_id', '=', loan.id)]
        loan.action_submit()
        first = self.env['mail.mail'].search(domain)
        self.assertEqual(len(first), 1)
        self.assertIn(self.hr_user.email, first.email_to)
        self.assertNotIn(finance.email, first.email_to)
        loan.action_approve()
        second = self.env['mail.mail'].search(domain) - first
        self.assertEqual(len(second), 1)
        self.assertIn(finance.email, second.email_to)
        self.assertNotIn(self.hr_user.email, second.email_to)
        self.assertIn('model=hr.loan', second.body_html)
        with self.assertRaises(ValidationError):
            loan.action_approve()
        self.assertEqual(self.env['mail.mail'].search_count(domain), 2)

    def test_nonpositive_installments_cannot_submit(self):
        for count in (0, -1):
            with self.assertRaises(ValidationError):
                self._loan(installment=count).action_submit()

    def test_finance_can_post_after_hr_and_cannot_post_twice(self):
        finance = self._finance()
        loan = self._loan()
        loan.write({
            'employee_account_id': self.env['account.account'].search([
                ('account_type', '=', 'asset_current')], limit=1).id,
            'treasury_account_id': self.env['account.account'].search([
                ('account_type', '=', 'asset_cash')], limit=1).id,
            'journal_id': self.env['account.journal'].search([('type', '=', 'general')], limit=1).id,
        })
        self.assertTrue(loan.employee_account_id and loan.treasury_account_id and loan.journal_id)
        loan.action_submit()
        loan.with_user(self.hr_user).action_approve()
        loan.with_user(finance).action_double_approve()
        self.assertEqual(loan.state, 'approve')
        self.assertEqual(loan.finance_approved_by, finance)
        moves = self.env['account.move'].search([('ref', '=', loan.name)])
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves.state, 'posted')
        with self.assertRaises(ValidationError):
            loan.with_user(finance).action_double_approve()

    def test_future_advance_rejected_and_day_31_capped(self):
        with patch.object(fields.Date, 'context_today', return_value=date(2026, 9, 8)):
            with self.assertRaises(ValidationError):
                self.env['salary.advance'].create({'employee_id': self.employee.id,
                                                  'date': '2026-09-30', 'advance': 3000})
        with patch.object(fields.Date, 'context_today', return_value=date(2026, 10, 31)):
            advance = self.env['salary.advance'].create({'employee_id': self.employee.id,
                                                        'date': '2026-10-31', 'advance': 3000})
            self.assertEqual(advance.earned_to_date, 3000)
