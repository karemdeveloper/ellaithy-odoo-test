from odoo import _, api, fields, models
from odoo.exceptions import UserError

# What HR can upload, the model it lands in, and the columns to prepare.
# Entries whose model is not installed are not offered.
DATA_TYPES = [
    ('employees', 'Employees', 'hr.employee',
     'Employee Code, Employee Name, Arabic Name, Department, Section, Job Position, '
     'Branch, Grade, Work Email, Work Mobile, Private Phone, Joining Date, '
     'Identification No, Date of Birth, Manager. A row with an existing '
     'Employee Code updates that employee.'),
    ('contracts', 'Contracts', 'hr.contract',
     'Contract Reference, Employee (code), Start Date, End Date, Wage, Insurance '
     'Salary, Total Salary, allowances, Status.'),
    ('departments', 'Departments and Sections', 'hr.department',
     'Department Name, Arabic Name, Type (Directorate / Section), Parent '
     'Department, Sector, Manager.'),
    ('branches', 'Branches', 'ellithy.branch',
     'Branch Name, Arabic Name, Code, Branch Head, Address, Phone.'),
    ('jobs', 'Job Positions', 'hr.job',
     'Job Position, Department, Section, Job Grade.'),
    ('fingerprints', 'Fingerprint Punches', 'ibs.hr.punch.import.wizard',
     'Employee code (or badge ID) and the punch date-time, one punch per row, '
     'exactly as the device exports them. Punches are paired per day into '
     'attendance.'),
    ('leave_adjustments', 'Leave Balance Adjustments', 'ibs.hr.time.off.ledger',
     'Employee, Type, Date, Amount (days, negative to deduct), Entry Type = '
     'Adjustment, Description. Use it for opening balances.'),
    ('warnings', 'Disciplinary Penalties', 'ibs.hr.warning',
     'Employee, Violation, Date, Override (days), Notes.'),
    ('admin_penalties', 'Administrative Penalties', 'ibs.hr.admin.penalty.record',
     'Employee, Penalty, Date, Override Cost, Notes.'),
    ('commission_penalties', 'Commission Penalties', 'ibs.hr.commission.penalty',
     'Employee, Percentage, Reason (name or code from the reason list), Date, Notes.'),
]


class EllithyDataImportWizard(models.TransientModel):
    """One door for every Excel upload HR does.

    Each choice opens Odoo's own import for that data, which maps the
    columns, offers a template and a "Test" pass that reports every bad row
    before anything is written.
    """

    _name = 'ellithy.data.import.wizard'
    _description = 'Data Upload'

    @api.model
    def _selection_data_type(self):
        return [(key, label) for key, label, model, _cols in DATA_TYPES
                if model in self.env]

    data_type = fields.Selection(
        selection='_selection_data_type', string='Data to Upload',
        required=True, default='employees')
    columns_help = fields.Text(
        string='Columns to Prepare', compute='_compute_columns_help')

    @api.depends('data_type')
    def _compute_columns_help(self):
        helps = {key: cols for key, _label, _model, cols in DATA_TYPES}
        for wizard in self:
            wizard.columns_help = helps.get(wizard.data_type, '')

    def action_open_import(self):
        self.ensure_one()
        model = {key: model for key, _l, model, _c in DATA_TYPES}[self.data_type]
        if model not in self.env:
            raise UserError(_('This kind of data is not available here.'))
        if self.data_type == 'fingerprints':
            return {
                'type': 'ir.actions.act_window', 'name': _('Import Fingerprint Punches'),
                'res_model': model, 'view_mode': 'form', 'target': 'new',
            }
        self.env[model].check_access('create')
        return {
            'type': 'ir.actions.client',
            'tag': 'import',
            'params': {'model': model, 'context': dict(self.env.context)},
        }
