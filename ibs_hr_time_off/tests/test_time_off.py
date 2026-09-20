from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged('post_install', '-at_install', 'ibs_hr_time_off')
class TestCustomTimeOff(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Time Off Employee',
            'joining_date': '2026-01-01',
            'birthday': '1990-09-14',
        })
        cls.shift = cls.env['ibs.hr.shift'].create({
            'name': 'Test Shift',
            'from_date': '2026-01-01',
            'to_date': '2027-12-31',
            'line_ids': [(0, 0, {
                'day': str(day), 'from_time': 9.0, 'to_time': 17.0,
            }) for day in range(7)],
        })
        cls.employee.shift_id = cls.shift
        cls.casual = cls.env.ref('ibs_hr_time_off.time_off_type_casual')
        cls.annual = cls.env.ref('ibs_hr_time_off.time_off_type_annual')
        cls.birthday = cls.env.ref('ibs_hr_time_off.time_off_type_birthday')

    def _request(self, time_off_type, day='2026-09-14'):
        return self.env['ibs.hr.time.off.request'].create({
            'employee_id': self.employee.id,
            'type_id': time_off_type.id,
            'date_from': day,
            'date_to': day,
        })

    def test_casual_grant_and_usage(self):
        request = self._request(self.casual)
        request.action_submit()
        self.assertAlmostEqual(request._balance_on(request.date_from), 7.0)
        request.action_hr_approve()
        self.assertEqual(request.state, 'approved')
        self.assertAlmostEqual(request._balance_on(request.date_from), 6.0)

    def test_january_joiner_accrues_on_monthly_anniversaries(self):
        request = self._request(self.annual, '2026-12-31')
        request._ensure_entitlements(date(2026, 12, 31))
        entries = self.env['ibs.hr.time.off.ledger'].search([
            ('employee_id', '=', self.employee.id),
            ('type_id', '=', self.annual.id),
            ('entry_type', '=', 'accrual'),
        ])
        self.assertEqual(len(entries), 9)
        self.assertAlmostEqual(sum(entries.mapped('amount')), 7.3333)
        request._ensure_entitlements(date(2026, 12, 31))
        self.assertEqual(len(self.env['ibs.hr.time.off.ledger'].search([
            ('employee_id', '=', self.employee.id),
            ('type_id', '=', self.annual.id),
            ('entry_type', '=', 'accrual'),
        ])), 9)

    def test_old_service_year_postings_replaced_without_changing_evidence(self):
        request = self._request(self.annual, '2026-08-31')
        ledger = self.env['ibs.hr.time.off.ledger']
        originals = ledger.create([{
            'employee_id': self.employee.id, 'type_id': self.annual.id,
            'date': day, 'amount': 1.6667, 'entry_type': 'accrual',
            'unique_key': 'annual:%s:%s:%s' % (self.employee.id, self.annual.id, day),
        } for day in ['2026-04-30', '2026-05-31', '2026-06-30', '2026-07-31', '2026-08-31']])
        amounts = originals.mapped('amount')
        request._ensure_entitlements(date(2026, 8, 31))
        self.assertEqual(originals.mapped('amount'), amounts)
        self.assertAlmostEqual(request._balance_on(date(2026, 8, 31)), 4.6667)
        count = ledger.search_count([('employee_id', '=', self.employee.id)])
        request._ensure_entitlements(date(2026, 8, 31))
        self.assertEqual(ledger.search_count([('employee_id', '=', self.employee.id)]), count)

    def test_september_joiner_december_grants_and_january_reset(self):
        self.employee.joining_date = '2026-09-01'
        annual = self._request(self.annual, '2026-12-01')
        casual = self._request(self.casual, '2026-12-01')
        self.assertEqual(annual._balance_on(date(2026, 11, 30)), 0)
        self.assertEqual(casual._balance_on(date(2026, 11, 30)), 0)
        self.assertEqual(annual._balance_on(date(2026, 12, 1)), 2)
        self.assertEqual(casual._balance_on(date(2026, 12, 1)), 7)
        self.assertAlmostEqual(annual._balance_on(date(2027, 1, 1)), 0.6667)
        self.assertEqual(casual._balance_on(date(2027, 1, 1)), 7)
        self.assertAlmostEqual(annual._balance_on(date(2027, 2, 1)), 1.3333)
        self.assertAlmostEqual(annual._balance_on(date(2027, 8, 1)), 5.3333)
        self.assertAlmostEqual(annual._balance_on(date(2027, 9, 1)), 6.5)
        self.assertEqual(self.employee._annual_leave_days(date(2027, 9, 1)), 14)
        mature = self._request(self.annual, '2028-12-31')
        self.assertEqual(mature._balance_on(date(2028, 12, 31)), 14)

    def test_month_end_joiner_uses_original_joining_day(self):
        self.employee.joining_date = '2026-08-31'
        request = self._request(self.annual, '2026-11-30')
        self.assertEqual(request._balance_on(date(2026, 11, 29)), 0)
        self.assertEqual(request._balance_on(date(2026, 11, 30)), 2)
        self.assertAlmostEqual(request._balance_on(date(2026, 12, 30)), 2)
        self.assertAlmostEqual(request._balance_on(date(2026, 12, 31)), 2.6667)
        # January's credit is posted on the 31st, after old credit expires.
        self.assertEqual(request._balance_on(date(2027, 1, 1)), 0)
        self.assertAlmostEqual(request._balance_on(date(2027, 1, 31)), 0.6667)

    def test_cancel_previous_year_leave_does_not_restore_current_year_credit(self):
        self.employee.joining_date = '2026-09-01'
        request = self._request(self.annual, '2026-12-01')
        request.action_submit()
        request.action_hr_approve()
        self.assertEqual(request._balance_on(date(2026, 12, 31)), 1)
        self.assertAlmostEqual(request._balance_on(date(2027, 1, 1)), 0.6667)
        request.action_cancel()
        self.assertAlmostEqual(request._balance_on(date(2027, 1, 1)), 0.6667)

    def test_cross_year_request_consumes_each_year_separately(self):
        self.employee.joining_date = '2026-09-01'
        request = self._request(self.annual, '2026-12-31')
        request.date_to = '2027-01-01'
        with self.assertRaises(ValidationError):
            request.action_submit()
        self.env['ibs.hr.time.off.ledger'].create({
            'employee_id': self.employee.id, 'type_id': self.annual.id,
            'date': '2027-01-01', 'amount': 1, 'entry_type': 'adjustment'})
        request.action_submit()
        request.action_hr_approve()
        usage = self.env['ibs.hr.time.off.ledger'].search([
            ('request_id', '=', request.id), ('entry_type', '=', 'usage')])
        self.assertEqual(len(usage), 2)
        self.assertEqual(set(usage.mapped('amount')), {-1})
        self.assertEqual(request._balance_on(date(2026, 12, 31)), 1)
        self.assertAlmostEqual(request._balance_on(date(2027, 1, 1)), 0.6667)

    def test_birthday_can_be_reserved_once_per_year(self):
        first = self._request(self.birthday)
        first.action_submit()
        with self.assertRaises(ValidationError):
            self._request(self.birthday).action_submit()

    def test_required_three_month_period(self):
        request = self._request(self.casual, '2026-03-31')
        with self.assertRaises(ValidationError):
            request.action_submit()

    def test_public_holiday_occurrence_cannot_be_reserved_twice(self):
        holiday_type = self.env.ref(
            'ibs_hr_time_off.time_off_type_public_holiday')
        holiday = self.env['ibs.hr.public.holiday'].create({
            'name': 'Worked Holiday',
            'date': '2026-07-23',
        })
        first = self._request(holiday_type, '2026-09-14')
        first.holiday_id = holiday
        first.action_submit()
        second = self._request(holiday_type, '2026-09-15')
        second.holiday_id = holiday
        with self.assertRaises(ValidationError):
            second.action_submit()

    def test_approved_custom_time_off_sets_daily_leave_status(self):
        request = self._request(self.casual)
        request.action_submit()
        request.action_hr_approve()
        self.env['ibs.hr.attendance.day'].generate_days(
            request.date_from, request.date_to, self.employee)
        day = self.env['ibs.hr.attendance.day'].search([
            ('employee_id', '=', self.employee.id),
            ('date', '=', request.date_from),
        ])
        self.assertEqual(day.state, 'leave')
        self.assertTrue(day.is_paid_leave)
