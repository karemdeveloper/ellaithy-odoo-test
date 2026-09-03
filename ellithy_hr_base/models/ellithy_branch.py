from odoo import fields, models


class EllithyBranch(models.Model):
    """Physical branch.

    Odoo Community has no branch concept, and modelling branches as companies
    would force multi-company record rules onto every HR document. The legacy
    ``branches`` table is therefore reproduced as its own model, referenced
    from the employee rather than derived from the department: the source data
    has staff of one department sitting in several branches.
    """

    _name = 'ellithy.branch'
    _description = 'Branch'
    _order = 'sequence, name'

    name = fields.Char(string='Branch Name', required=True, translate=False)
    name_ar = fields.Char(string='Arabic Name')
    code = fields.Char(string='Code')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    company_id = fields.Many2one(
        'res.company', string='Company', required=True,
        default=lambda self: self.env.company, ondelete='restrict')
    manager_id = fields.Many2one(
        'hr.employee', string='Branch Head', ondelete='set null')

    address = fields.Char()
    phone = fields.Char()

    # The legacy stores these as required. Combined with the NFC/QR attendance
    # flag they point at geofenced check-in -- see ellithy_hr_attendance.
    latitude = fields.Float(string='Latitude', digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))

    department_ids = fields.One2many(
        'hr.department', 'branch_id', string='Departments')
    employee_ids = fields.One2many(
        'hr.employee', 'branch_id', string='Employees')
    employee_count = fields.Integer(
        string='Employee Count', compute='_compute_employee_count')

    legacy_id = fields.Integer(
        string='Legacy ID', index=True, copy=False,
        help='Primary key in the source MariaDB database. Keeps migration '
             'runs idempotent and reconcilable.')

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another branch already carries this legacy ID.'),
    ]

    def _compute_employee_count(self):
        data = self.env['hr.employee']._read_group(
            [('branch_id', 'in', self.ids)], ['branch_id'], ['__count'])
        mapped = {branch.id: count for branch, count in data}
        for record in self:
            record.employee_count = mapped.get(record.id, 0)

    def action_view_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'hr.employee',
            'view_mode': 'kanban,list,form',
            'domain': [('branch_id', '=', self.id)],
            'context': {'default_branch_id': self.id},
        }
