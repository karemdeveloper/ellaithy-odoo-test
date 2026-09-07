from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestBlankForms(IbsHrCommon):
    """Opening a new record must not raise.

    Every compute runs once against an empty record before the user has
    chosen anything, so any compute that reaches a singleton helper through
    an unset Many2one will crash the form on open. The original failure was
    ibs.hr.warning: _compute_deducted_amount called _daily_rate, which called
    employee_id._ibs_contract_on() on an empty hr.employee.

    These read every stored computed field on a fresh record, which is what
    the web client does when it builds the form.
    """

    def _open_blank(self, model_name, defaults=None):
        model = self.env[model_name]
        record = model.new(defaults or {})
        computed = [
            name for name, field in model._fields.items()
            if field.compute and field.store
        ]
        for name in computed:
            record[name]  # must not raise
        return record

    def test_blank_warning_form(self):
        record = self._open_blank('ibs.hr.warning')
        self.assertEqual(record.deducted_amount, 0.0)
        self.assertEqual(record.penalty_days, 0.0)

    def test_blank_warning_with_employee_but_no_violation(self):
        """Half-filled is the state the form spends most of its time in."""
        record = self._open_blank(
            'ibs.hr.warning', {'employee_id': self.employee.id})
        self.assertEqual(record.deducted_amount, 0.0)

    def test_blank_warning_with_violation_but_no_employee(self):
        violation = self.env['ibs.hr.violation'].create({
            'name': 'Blank probe',
            'penalty_ids': [(0, 0, {'occurrence': 1, 'action': 'fine',
                                    'penalty_days': 1.0})],
        })
        record = self._open_blank(
            'ibs.hr.warning', {'violation_id': violation.id})
        self.assertEqual(record.deducted_amount, 0.0)

    def test_blank_payslip_form(self):
        record = self._open_blank('hr.payslip')
        self.assertEqual(record.penalty_days_taken, 0.0)
        self.assertEqual(record.penalty_days_deferred, 0.0)

    def test_blank_loan_form(self):
        record = self._open_blank('hr.loan')
        self.assertEqual(record.balance_amount, 0.0)

    def test_blank_salary_advance_form(self):
        record = self._open_blank('salary.advance')
        self.assertFalse(record.advance)

    def test_blank_attendance_day_form(self):
        record = self._open_blank('ibs.hr.attendance.day')
        self.assertEqual(record.worked_hours, 0.0)
        self.assertEqual(record.absence_days, 0.0)

    def test_blank_branch_form(self):
        record = self._open_blank('ellithy.branch')
        self.assertEqual(record.employee_count, 0)

    def test_blank_employee_form(self):
        record = self._open_blank('hr.employee')
        self.assertEqual(record.dependant_count, 0)

    def test_daily_rate_without_employee_is_zero(self):
        record = self.env['ibs.hr.warning'].new({'date': '2026-06-01'})
        self.assertEqual(record._daily_rate(), 0.0)

    def test_daily_rate_without_date_is_zero(self):
        """date must be cleared explicitly -- it defaults to today, so simply
        omitting it still yields a usable rate once an employee is chosen."""
        record = self.env['ibs.hr.warning'].new(
            {'employee_id': self.employee.id, 'date': False})
        self.assertEqual(record._daily_rate(), 0.0)

    def test_daily_rate_defaults_to_today_once_employee_chosen(self):
        record = self.env['ibs.hr.warning'].new(
            {'employee_id': self.employee.id})
        self.assertTrue(record.date)
        self.assertAlmostEqual(record._daily_rate(), 100.0, places=2)

    def test_contract_lookup_on_empty_employee(self):
        empty = self.env['hr.employee']
        self.assertFalse(empty._ibs_contract_on('2026-06-01'))
