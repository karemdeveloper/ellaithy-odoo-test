import base64
from zoneinfo import available_timezones

from odoo import api, fields, models, _
from odoo.exceptions import UserError

from ..models.attendance_import import _INTERNAL
from ..services.parser import open_excel


class AttendanceImportWizard(models.TransientModel):
    _name = 'hr.attendance.excel.import.wizard'
    _description = 'Upload Excel Attendances'

    @api.model
    def _default_code_field_id(self):
        employee = self.env['hr.employee']
        field = employee._fields.get('employee_code')
        if (not field or not field.store or field.company_dependent
                or employee.fields_get(['employee_code']).get('employee_code', {}).get('type') != 'char'):
            return False
        return self.env['ir.model.fields'].search([
            ('model', '=', 'hr.employee'), ('name', '=', 'employee_code'),
            ('ttype', '=', 'char'), ('store', '=', True),
        ], limit=1).id

    file_data = fields.Binary(required=True, attachment=False)
    filename = fields.Char(required=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    code_field_id = fields.Many2one('ir.model.fields', string='Employee Code Field', required=True,
                                  default=_default_code_field_id,
                                  domain="[('model', '=', 'hr.employee'), ('ttype', '=', 'char'), ('store', '=', True)]")
    timezone = fields.Selection(selection=lambda self: [(tz, tz) for tz in sorted(available_timezones())],
                                required=True, default=lambda self: self.env.company.resource_calendar_id.tz or self.env.user.tz)
    sheet_number = fields.Integer(string='Worksheet Number (1-based)', default=1, required=True)
    worksheet_names = fields.Text(readonly=True)
    duplicate_policy = fields.Selection([('skip', 'Skip Existing'), ('conflict', 'Report Conflicts'),
                                         ('update', 'Update Existing')], default='skip', required=True)
    missing_policy = fields.Selection([('strict', 'Strict'), ('open', 'Allow Open Attendance'),
                                       ('skip', 'Skip Incomplete')], default='strict', required=True)
    approve_manual = fields.Boolean(string='I approve updating existing records not created by this importer')
    max_hours = fields.Float(string='Maximum Shift Hours', default=16, required=True)
    max_rows = fields.Integer(string='Maximum Rows', default=10000, required=True)
    max_mb = fields.Integer(string='Maximum File Size (MB)', default=10, required=True)

    @api.onchange('file_data')
    def _onchange_file(self):
        self.worksheet_names = False
        if self.file_data:
            try:
                book = open_excel(base64.b64decode(self.with_context(bin_size=False).file_data, validate=True), min(self.max_mb or 10, 50))
                try:
                    self.worksheet_names = '\n'.join('%s: %s' % (i, name) for i, name in enumerate(book.sheetnames, 1))
                finally:
                    book.close()
            except ValueError as exc:
                raise UserError(str(exc)) from exc

    def action_preview(self):
        self.ensure_one()
        self.env['hr.attendance.excel.import']._authorize()
        if self.company_id not in self.env.companies:
            raise UserError(_('Choose a company currently enabled for your user.'))
        if not self.filename.lower().endswith('.xlsx'):
            raise UserError(_('Only .xlsx workbooks are supported.'))
        if not (0 < self.max_hours <= 48 and 0 < self.max_rows <= 50000 and 0 < self.max_mb <= 50):
            raise UserError(_('Limits: 1–50000 rows, 1–50 MB, and more than 0 up to 48 shift hours.'))
        if self.code_field_id.model != 'hr.employee':
            raise UserError(_('Select a field on hr.employee.'))
        vals = {name: self[name] for name in (
            'file_data', 'filename', 'timezone', 'sheet_number', 'duplicate_policy', 'missing_policy',
            'approve_manual', 'max_hours', 'max_rows', 'max_mb')}
        vals.update(company_id=self.company_id.id, code_field=self.code_field_id.name)
        vals['file_data'] = self.with_context(bin_size=False).file_data
        batch = self.env['hr.attendance.excel.import'].with_context(_attendance_internal=_INTERNAL).create(vals)
        batch.action_validate()
        return batch._open()
