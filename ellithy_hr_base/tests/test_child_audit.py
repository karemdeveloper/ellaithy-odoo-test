from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestEmployeeChildAudit(TransactionCase):
    def test_dependant_create_update_delete_are_logged(self):
        employee = self.env['hr.employee'].create({'name': 'Audit employee'})
        before = employee.message_ids
        child = self.env['ellithy.hr.dependant'].create({'employee_id': employee.id, 'name': 'First name'})
        child.name = 'Second name'
        child.unlink()
        notes = employee.message_ids - before
        self.assertEqual(len(notes), 3)
        body = '\n'.join(notes.mapped('body'))
        for text in ('Created', 'Updated', 'Deleted', 'First name', 'Second name'):
            self.assertIn(text, body)

    def test_document_replacement_and_account_edits_are_logged(self):
        employee = self.env['hr.employee'].create({'name': 'Audit documents'})
        document = employee.document_ids[:1]
        before = employee.message_ids
        document.write({'copy_type': 'original', 'document': b'YQ==', 'filename': 'first.txt'})
        document.write({'document': b'Yg==', 'filename': 'second.txt'})
        account = self.env['ellithy.hr.account'].create({
            'employee_id': employee.id, 'account_number': '111'})
        account.account_number = '222'
        notes = employee.message_ids - before
        body = '\n'.join(notes.mapped('body'))
        self.assertIn('first.txt', body)
        self.assertIn('second.txt', body)
        self.assertIn('111', body)
        self.assertIn('222', body)
        self.assertNotIn('YQ==', body)

    def test_document_update_log_always_shows_document_type(self):
        employee = self.env['hr.employee'].create({'name': 'Audit document type'})
        document = employee.document_ids[:1]
        type_name = document.type_id.display_name
        before = employee.message_ids
        # The type itself does not change on either write, only the file.
        document.write({'copy_type': 'original', 'document': b'YQ==', 'filename': 'first.txt'})
        document.write({'document': b'Yg==', 'filename': 'second.txt'})
        notes = (employee.message_ids - before).filtered(lambda m: 'Updated' in m.body)
        self.assertEqual(len(notes), 2)
        for note in notes:
            self.assertIn(type_name, note.body)

    def test_long_scalar_change_is_not_truncated(self):
        employee = self.env['hr.employee'].create({'name': 'Audit long value'})
        employee.blacklist_reason = 'A' * 200 + 'END'
        self.assertTrue(any('A' * 200 + 'END' in m.body for m in employee.message_ids))

    def test_employee_binary_and_tags_are_logged_without_file_content(self):
        employee = self.env['hr.employee'].create({'name': 'Audit files and tags'})
        category = self.env['hr.employee.category'].create({'name': 'Audit tag'})
        before = employee.message_ids
        employee.write({'id_card': b'YQ==', 'category_ids': [(4, category.id)]})
        employee.id_card = b'Yg=='
        notes = '\n'.join((employee.message_ids - before).mapped('body'))
        self.assertIn('File fingerprint', notes)
        self.assertIn('Audit tag', notes)
        self.assertNotIn('YQ==', notes)
