from odoo import fields, models


class EllithyHrGrade(models.Model):
    """Job grade ladder.

    Six ordered levels held on the employee independently of the position.
    ``sequence`` carries the ordering so grade comparisons and approval
    thresholds work rather than relying on alphabetical order.
    """

    _name = 'ellithy.hr.grade'
    _description = 'Employee Grade'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    name_ar = fields.Char(string='Arabic Name')
    sequence = fields.Integer(default=10, help='Lower is more junior.')
    active = fields.Boolean(default=True)
    employee_ids = fields.One2many('hr.employee', 'grade_id', string='Employees')
    legacy_value = fields.Char(
        string='Legacy Value', index=True,
        help='Raw value stored in the legacy users.grade column.')
