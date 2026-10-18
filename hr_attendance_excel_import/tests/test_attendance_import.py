import base64
from datetime import datetime

from odoo import Command
from odoo.exceptions import AccessError, UserError
from odoo.tests import TransactionCase, tagged
from odoo.tools.convert import convert_file
from odoo import sql_db
from psycopg2.errors import LockNotAvailable

from ..models.attendance_import import _INTERNAL
from .test_parser import workbook_bytes


@tagged('post_install', '-at_install')
class TestAttendanceImport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.manager = cls.env['res.users'].create({
            'name': 'Import Manager', 'login': 'attendance-import-test-manager',
            'company_id': cls.company.id, 'company_ids': [Command.set(cls.company.ids)],
            'groups_id': [Command.set([cls.env.ref('hr_attendance.group_hr_attendance_manager').id,
                                       cls.env.ref('hr.group_hr_user').id])],
        })
        cls.employee = cls.env['hr.employee'].create({
            'name': 'Test Employee', 'identification_id': 'EMP-892', 'company_id': cls.company.id,
        })
        cls.code_field = cls.env['ir.model.fields']._get('hr.employee', 'identification_id')

    def upload(self, rows=None, **settings):
        vals = {
            'file_data': base64.b64encode(workbook_bytes(rows if rows is not None else [
                ['EMP-892', '2026-09-02', '08:00', '16:00']])),
            'filename': 'test.xlsx', 'company_id': self.company.id,
            'code_field_id': self.code_field.id, 'timezone': 'UTC',
        }
        vals.update(settings)
        return self.env['hr.attendance.excel.import.wizard'].with_user(self.manager).create(vals)

    def preview(self, rows=None, **settings):
        action = self.upload(rows, **settings).action_preview()
        return self.env['hr.attendance.excel.import'].with_user(self.manager).browse(action['res_id'])

    def test_valid_and_code_matching(self):
        batch = self.preview()
        self.assertEqual(batch.line_ids.employee_id, self.employee)
        batch.action_import()
        self.assertEqual(batch.imported, 1)
        self.assertEqual(batch.line_ids.attendance_id.check_in, datetime(2026, 9, 2, 8))

    def test_unknown_employee(self):
        batch = self.preview([['UNKNOWN', '2026-09-02', '08:00', '16:00']])
        self.assertEqual(batch.failed, 1)

    def test_duplicate_employee_code(self):
        self.employee.copy({'name': 'Ambiguous', 'identification_id': 'EMP-892'})
        self.assertIn('Ambiguous', self.preview().line_ids.message)

    def test_duplicate_file_rows(self):
        batch = self.preview([['EMP-892', '2026-09-02', '08:00', '16:00']] * 2)
        self.assertEqual(batch.duplicates, 1)
        batch.action_import()
        self.assertEqual(batch.imported, 1)

    def test_reimport(self):
        self.preview().action_import()
        batch = self.preview()
        self.assertEqual(batch.duplicates, 1)
        batch.action_import()
        self.assertEqual(batch.imported, 0)

    def test_overnight_timezone(self):
        batch = self.preview([['EMP-892', '2026-09-02', '13:48:22', '00:05:44']], timezone='Africa/Cairo')
        batch.action_import()
        self.assertEqual(batch.line_ids.attendance_id.check_out, datetime(2026, 9, 2, 21, 5, 44))

    def test_missing_and_invalid_punches(self):
        for start, end in [(None, '16:00'), ('08:00', None), ('bad', '16:00')]:
            batch = self.preview([['EMP-892', '2026-09-02', start, end]])
            self.assertEqual(batch.failed, 1)

    def test_leave(self):
        batch = self.preview([['EMP-892', '2026-09-02', 'إجازة', 'إجازة']])
        self.assertEqual(batch.skipped, 1)

    def test_overlap_and_multiple_sessions(self):
        batch = self.preview([['EMP-892', '2026-09-02', '08:00', '12:00'],
                              ['EMP-892', '2026-09-02', '12:00', '16:00'],
                              ['EMP-892', '2026-09-02', '15:00', '17:00']])
        self.assertEqual(batch.failed, 1)
        batch.action_import()
        self.assertEqual(batch.imported, 2)

    def test_existing_overlap(self):
        self.preview().action_import()
        batch = self.preview([['EMP-892', '2026-09-02', '15:00', '18:00']])
        self.assertEqual(batch.failed, 1)

    def test_open_attendance(self):
        batch = self.preview([['EMP-892', '2026-09-02', '08:00', None]], missing_policy='open')
        batch.action_import()
        self.assertFalse(batch.line_ids.attendance_id.check_out)
        self.assertEqual(self.preview([['EMP-892', '2026-09-03', '08:00', '16:00']]).failed, 1)

    def test_update_existing(self):
        first = self.preview()
        first.action_import()
        batch = self.preview([['EMP-892', '2026-09-02', '08:00', '17:00']], duplicate_policy='update')
        batch.action_import()
        self.assertEqual(batch.line_ids.attendance_id, first.line_ids.attendance_id)
        self.assertEqual(first.line_ids.attendance_id.check_out, datetime(2026, 9, 2, 17))

    def test_manual_update_requires_approval(self):
        record = self.env['hr.attendance'].create({'employee_id': self.employee.id,
            'check_in': '2026-09-02 08:00:00', 'check_out': '2026-09-02 15:00:00'})
        self.assertEqual(self.preview(duplicate_policy='update').failed, 1)
        batch = self.preview(duplicate_policy='update', approve_manual=True)
        batch.action_import()
        self.assertEqual(record.check_out, datetime(2026, 9, 2, 16))

    def test_company_scope(self):
        other = self.env['res.company'].create({'name': 'Import Other Company'})
        self.env['hr.employee'].create({'name': 'Other', 'identification_id': 'OTHER', 'company_id': other.id})
        self.assertEqual(self.preview([['OTHER', '2026-09-02', '08:00', '16:00']]).failed, 1)
        with self.assertRaises((AccessError, UserError)):
            self.preview(company_id=other.id)

    def test_unauthorized(self):
        user = self.env['res.users'].create({'name': 'Regular User', 'login': 'attendance-import-regular',
            'groups_id': [Command.set([self.env.ref('base.group_user').id])]})
        batch = self.preview()
        with self.assertRaises(AccessError):
            batch.with_user(user).action_import()

    def test_malformed_and_oversized(self):
        with self.assertRaises(UserError):
            self.upload(file_data=base64.b64encode(b'bad')).action_preview()
        with self.assertRaises(UserError):
            self.upload(file_data=base64.b64encode(b'x' * (1024 * 1024 + 1)), max_mb=1).action_preview()

    def test_preview_tamper(self):
        batch = self.preview()
        with self.assertRaises(AccessError):
            batch.line_ids.write({'check_in': '2026-09-02 01:00:00'})
        batch.write({'line_ids': [Command.update(batch.line_ids.id, {'approved': False})]})
        batch.action_import()
        self.assertEqual(batch.skipped, 1)

    def test_revalidation_conflict(self):
        batch = self.preview()
        self.preview([['EMP-892', '2026-09-02', '07:00', '09:00']]).action_import()
        batch.action_import()
        self.assertEqual(batch.imported, 0)
        self.assertEqual(batch.failed, 1)

    def test_guard_xml_replay_preserves_identity_and_revision(self):
        guard = self.env.ref('hr_attendance_excel_import.serialization_guard')
        self.assertEqual(guard._name, 'hr.attendance.excel.import.lock')
        self.assertTrue(guard.exists())
        guard.with_context(_attendance_internal=_INTERNAL).write({'revision': 7})
        for mode in ('init', 'update'):
            with self.subTest(mode=mode):
                convert_file(self.env, 'hr_attendance_excel_import',
                             'security/security.xml', {}, mode=mode, kind='data')
                reloaded = self.env.ref('hr_attendance_excel_import.serialization_guard')
                reloaded.invalidate_recordset()
                self.assertEqual(reloaded.id, guard.id)
                self.assertEqual(reloaded.revision, 7)

    def test_guard_public_mutations_still_denied(self):
        guard = self.env.ref('hr_attendance_excel_import.serialization_guard').with_user(self.manager)
        for values in ({}, {'revision': 0}):
            with self.assertRaises(AccessError):
                guard.write(values)
        with self.assertRaises(AccessError):
            guard.unlink()
        # A context supplied over RPC is not the private in-process token.
        with self.assertRaises(AccessError):
            guard.with_context(_attendance_internal=True).write({'revision': 0})

    def test_guard_blocks_another_database_transaction(self):
        batch = self.preview()
        guard = self.env.ref('hr_attendance_excel_import.serialization_guard')
        before = guard.revision
        batch._lock()
        guard.invalidate_recordset()
        self.assertEqual(guard.revision, before + 1)
        # Use a real independent connection, not registry.cursor(), which can
        # share the test transaction through Odoo's TestCursor machinery.
        with sql_db.db_connect(self.env.cr.dbname).cursor() as other_cr:
            with self.assertRaises(LockNotAvailable):
                other_cr.execute(
                    'SELECT id FROM hr_attendance_excel_import_lock WHERE id = %s FOR UPDATE NOWAIT',
                    [guard.id],
                )
            other_cr.rollback()
