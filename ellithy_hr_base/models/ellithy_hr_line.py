from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# The legacy keeps five tables -- phones, lap_numbers, adsls, sms and
# data_numbers -- with identical columns (number, serial, bundle) differing
# only in who the line is assigned to. Five near-identical models would mean
# five copies of the same views, ACLs and constraints, so this is one model
# with a type selector and five filtered menu items.
LINE_TYPE = [
    ('phone', 'Work Number'),
    ('lap', 'Lap Number'),
    ('adsl', 'ADSL Number'),
    ('sms', 'SMS Number'),
    ('data', 'Data Number'),
]

# Which holder each type is assigned to, mirroring the legacy foreign keys.
HOLDER = {
    'phone': 'employee',   # phones.assigned_user
    'lap': 'employee',     # lap_numbers.user_id
    'adsl': 'department',  # adsls.department_id
    'sms': 'department',   # sms.department_id
    'data': 'section',     # data_numbers.post_id
}


class EllithyHrLine(models.Model):
    """A company telecom line or number held by an employee or department."""

    _name = 'ellithy.hr.line'
    _description = 'Company Line'
    _order = 'line_type, number'
    _rec_names_search = ['number', 'serial', 'bundle']

    number = fields.Char(required=True, index=True)
    line_type = fields.Selection(
        LINE_TYPE, string='Type', required=True, default='phone', index=True)
    serial = fields.Char(
        string='Serial',
        help='SIM ICCID for a phone line; asset serial otherwise.')
    bundle = fields.Char(
        string='Bundle', index=True,
        help='Tariff plan the line is subscribed to.')

    employee_id = fields.Many2one(
        'hr.employee', string='Assigned Employee', ondelete='set null',
        index=True)
    department_id = fields.Many2one(
        'hr.department', string='Assigned Department', ondelete='set null',
        domain="[('dept_type', '=', 'directorate')]")
    section_id = fields.Many2one(
        'hr.department', string='Assigned Section', ondelete='set null',
        domain="[('dept_type', '=', 'section')]")
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')

    holder_type = fields.Selection(
        [('employee', 'Employee'), ('department', 'Department'),
         ('section', 'Section')],
        string='Assigned To', compute='_compute_holder_type', store=True)
    holder_name = fields.Char(
        string='Holder', compute='_compute_holder_name', store=True)

    active = fields.Boolean(default=True)
    note = fields.Text()
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('number_type_uniq', 'unique(number, line_type)',
         'That number is already registered for this line type.'),
        ('legacy_type_uniq', 'unique(legacy_id, line_type)',
         'Another line of this type already carries that legacy ID.'),
    ]

    @api.depends('line_type')
    def _compute_holder_type(self):
        for record in self:
            record.holder_type = HOLDER.get(record.line_type, 'employee')

    @api.depends('holder_type', 'employee_id', 'department_id', 'section_id')
    def _compute_holder_name(self):
        for record in self:
            holder = {
                'employee': record.employee_id,
                'department': record.department_id,
                'section': record.section_id,
            }.get(record.holder_type)
            record.holder_name = holder.display_name if holder else False

    @api.onchange('line_type')
    def _onchange_line_type(self):
        """Clear a holder that no longer applies to the chosen type."""
        for record in self:
            holder = HOLDER.get(record.line_type)
            if holder != 'employee':
                record.employee_id = False
            if holder != 'department':
                record.department_id = False
            if holder != 'section':
                record.section_id = False

    @api.constrains('line_type', 'employee_id', 'department_id', 'section_id')
    def _check_holder(self):
        for record in self:
            holder = HOLDER.get(record.line_type)
            wrong = (
                (holder != 'employee' and record.employee_id)
                or (holder != 'department' and record.department_id)
                or (holder != 'section' and record.section_id)
            )
            if wrong:
                raise ValidationError(_(
                    'A %(type)s line is assigned to a %(holder)s, so the '
                    'other assignment fields must be empty.',
                    type=dict(LINE_TYPE).get(record.line_type),
                    holder=holder))

    def _compute_display_name(self):
        for record in self:
            label = dict(LINE_TYPE).get(record.line_type, '')
            record.display_name = f'{record.number} ({label})'
