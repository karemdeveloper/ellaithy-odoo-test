from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import IbsHrCommon


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestAdminPenalty(IbsHrCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.catalogue = cls.env['ibs.hr.admin.penalty'].create({
            'name': 'Late submission of report', 'cost': 250.0})

    def _record(self, **kwargs):
        values = {'employee_id': self.employee.id,
                  'penalty_id': self.catalogue.id, 'date': '2026-06-10'}
        values.update(kwargs)
        return self.env['ibs.hr.admin.penalty.record'].create(values)

    def test_snapshot_taken_on_create(self):
        """A later price change must not rewrite an issued penalty."""
        record = self._record()
        self.assertEqual(record.name_snapshot, 'Late submission of report')
        self.assertAlmostEqual(record.cost_snapshot, 250.0, places=2)
        self.catalogue.write({'name': 'Renamed', 'cost': 999.0})
        record.invalidate_recordset()
        self.assertEqual(record.name_snapshot, 'Late submission of report')
        self.assertAlmostEqual(record.amount, 250.0, places=2)

    def test_custom_cost_overrides_snapshot(self):
        record = self._record(custom_cost=100.0)
        self.assertAlmostEqual(record.amount, 100.0, places=2)

    def test_approval_flow(self):
        record = self._record()
        self.assertEqual(record.approval_status, 'pending')
        record.action_approve()
        self.assertEqual(record.approval_status, 'approved')
        self.assertTrue(record.approved_by)

    def test_cannot_approve_twice(self):
        record = self._record()
        record.action_approve()
        with self.assertRaises(ValidationError):
            record.action_approve()

    def test_rejection_requires_reason(self):
        record = self._record()
        with self.assertRaises(ValidationError):
            record.action_reject()
        record.rejection_reason = 'Not substantiated'
        record.action_reject()
        self.assertEqual(record.approval_status, 'rejected')


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestCommissionPenalty(IbsHrCommon):

    def test_percentage_bounds(self):
        for bad in (0.0, -5.0, 101.0):
            with self.subTest(pct=bad), self.assertRaises(ValidationError):
                self.env['ibs.hr.commission.penalty'].create({
                    'employee_id': self.employee.id, 'percentage': bad,
                    'reason': 'Probe'})

    def test_valid_percentage_accepted(self):
        record = self.env['ibs.hr.commission.penalty'].create({
            'employee_id': self.employee.id, 'percentage': 25.0,
            'reason': 'Target missed'})
        self.assertTrue(record.name.startswith('COMPEN/'))


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestInvestigation(IbsHrCommon):

    def test_employee_count_and_flow(self):
        investigation = self.env['ibs.hr.investigation'].create({
            'name': 'Stock discrepancy',
            'employee_ids': [(0, 0, {'employee_id': self.employee.id,
                                     'result': 'Cleared'})],
        })
        self.assertEqual(investigation.employee_count, 1)
        self.assertEqual(investigation.state, 'draft')
        investigation.action_open()
        self.assertEqual(investigation.state, 'open')
        investigation.action_close()
        self.assertEqual(investigation.state, 'closed')

    def test_same_employee_listed_once(self):
        investigation = self.env['ibs.hr.investigation'].create({
            'name': 'Duplicate probe'})
        self.env['ibs.hr.investigation.employee'].create({
            'investigation_id': investigation.id,
            'employee_id': self.employee.id})
        with self.assertRaises(Exception):
            self.env['ibs.hr.investigation.employee'].create({
                'investigation_id': investigation.id,
                'employee_id': self.employee.id})
            self.env.flush_all()


@tagged('post_install', '-at_install', 'ibs_payroll')
class TestPermissionMission(IbsHrCommon):

    def _request(self, **kwargs):
        values = {'employee_id': self.employee.id, 'issue_date': '2026-06-10',
                  'start_time': 9.0, 'end_time': 13.0}
        values.update(kwargs)
        return self.env['ibs.hr.permission'].create(values)

    def test_duration_computed(self):
        self.assertAlmostEqual(self._request().duration_hours, 4.0, places=2)

    def test_end_must_follow_start(self):
        with self.assertRaises(ValidationError):
            self._request(start_time=13.0, end_time=9.0)

    def test_times_must_be_within_the_day(self):
        with self.assertRaises(ValidationError):
            self._request(start_time=9.0, end_time=25.0)

    def test_mission_requires_a_destination(self):
        with self.assertRaises(ValidationError):
            self._request(kind='mission')
        mission = self._request(kind='mission', destination='Nasr City Branch')
        self.assertEqual(mission.kind, 'mission')

    def test_permission_needs_no_destination(self):
        self.assertFalse(self._request(kind='permission').destination)

    def test_sequence_differs_by_kind(self):
        permission = self._request()
        mission = self._request(kind='mission', destination='Zayed',
                                issue_date='2026-06-11')
        self.assertTrue(permission.name.startswith('PERM/'))
        self.assertTrue(mission.name.startswith('MIS/'))

    def test_approval_flow(self):
        request = self._request()
        request.action_submit()
        self.assertEqual(request.state, 'pending')
        request.action_approve()
        self.assertEqual(request.state, 'approved')

    def test_cannot_approve_from_draft(self):
        with self.assertRaises(ValidationError):
            self._request().action_approve()

    def test_rejection_requires_remark(self):
        request = self._request()
        request.action_submit()
        with self.assertRaises(ValidationError):
            request.action_reject()
        request.admin_remark = 'Not justified'
        request.action_reject()
        self.assertEqual(request.state, 'rejected')
