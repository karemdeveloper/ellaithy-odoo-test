from datetime import timedelta

from odoo.exceptions import ValidationError
from odoo.fields import Date
from odoo.tests import tagged

from .common import IbsHrPermissionCommon


@tagged('post_install', '-at_install', 'ibs_hr_permission')
class TestPermission(IbsHrPermissionCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lateness = cls.env.ref('ibs_hr_permission.permission_type_lateness')

    def _request(self, **kwargs):
        values = {
            'employee_id': self.employee.id,
            'permission_type_id': self.lateness.id,
            'issue_date': Date.context_today(self.env['ibs.hr.permission']),
            'duration_minutes': '30',
        }
        values.update(kwargs)
        return self.env['ibs.hr.permission'].create(values)

    def _make_admin(self):
        admin_group = self.env.ref('ellithy_hr_base.group_ellithy_hr_admin')
        self.env.user.write({'groups_id': [(4, admin_group.id)]})

    # -- duration dropdown --------------------------------------------

    def test_duration_choices_only(self):
        request = self._request(duration_minutes='90')
        self.assertAlmostEqual(request.duration_hours, 1.5, places=2)
        with self.assertRaises(Exception):
            self._request(duration_minutes='45')

    def test_sequence_prefix(self):
        request = self._request()
        self.assertTrue(request.name.startswith('PERM/'))

    # -- date window ----------------------------------------------------

    def test_date_window_rejects_far_dates(self):
        today = Date.context_today(self.env['ibs.hr.permission'])
        with self.assertRaises(ValidationError):
            self._request(issue_date=today - timedelta(days=3))
        with self.assertRaises(ValidationError):
            self._request(issue_date=today + timedelta(days=3))

    def test_date_window_allows_yesterday_today_tomorrow(self):
        today = Date.context_today(self.env['ibs.hr.permission'])
        for offset in (-1, 0, 1):
            request = self._request(issue_date=today + timedelta(days=offset))
            self.assertTrue(request.id)

    def test_admin_can_bypass_date_window(self):
        self._make_admin()
        today = Date.context_today(self.env['ibs.hr.permission'])
        request = self._request(issue_date=today - timedelta(days=30))
        self.assertTrue(request.id)

    # -- monthly cap ------------------------------------------------------

    def test_monthly_cap_allows_exact_limit(self):
        self._make_admin()
        self._request(issue_date='2026-03-05', duration_minutes='120')
        request = self._request(issue_date='2026-03-10', duration_minutes='120')
        self.assertTrue(request.id)  # exactly 240 minutes: allowed

    def test_monthly_cap_rejects_overage(self):
        self._make_admin()
        self._request(issue_date='2026-03-05', duration_minutes='120')
        self._request(issue_date='2026-03-10', duration_minutes='120')
        with self.assertRaises(ValidationError):
            self._request(issue_date='2026-03-15', duration_minutes='30')

    def test_monthly_cap_resets_next_month(self):
        self._make_admin()
        self._request(issue_date='2026-03-05', duration_minutes='120')
        self._request(issue_date='2026-03-10', duration_minutes='120')
        request = self._request(issue_date='2026-04-01', duration_minutes='120')
        self.assertTrue(request.id)

    def test_cancelled_excluded_from_cap(self):
        self._make_admin()
        first = self._request(issue_date='2026-03-05', duration_minutes='120')
        self._request(issue_date='2026-03-10', duration_minutes='120')
        first.action_cancel()
        third = self._request(issue_date='2026-03-15', duration_minutes='120')
        self.assertTrue(third.id)

    def test_custom_cap_via_config_parameter(self):
        self._make_admin()
        self.env['ir.config_parameter'].sudo().set_param(
            'ibs_hr_permission.monthly_cap_minutes', '60')
        self._request(issue_date='2026-03-05', duration_minutes='60')
        with self.assertRaises(ValidationError):
            self._request(issue_date='2026-03-06', duration_minutes='30')

    # -- approval workflow --------------------------------------------

    def test_approval_flow(self):
        request = self._request()
        request.action_submit()
        self.assertEqual(request.state, 'pending')
        request.action_approve()
        self.assertEqual(request.state, 'approved')

    def test_cannot_approve_from_draft(self):
        with self.assertRaises(ValidationError):
            self._request().action_approve()

    def test_reject_needs_no_remark(self):
        """Unlike Mission, Permission has no admin remark to require."""
        request = self._request()
        request.action_submit()
        request.action_reject()
        self.assertEqual(request.state, 'rejected')

    def test_cancel_and_reset(self):
        request = self._request()
        request.action_submit()
        request.action_cancel()
        self.assertEqual(request.state, 'cancelled')
        request.action_reset()
        self.assertEqual(request.state, 'draft')
