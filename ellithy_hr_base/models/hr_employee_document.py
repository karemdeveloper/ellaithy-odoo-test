from odoo import fields, models


class EllithyHrDocument(models.Model):
    """One HR file document held for an employee.

    Replaces the fourteen fixed upload columns on the legacy ``users`` table.
    """

    _name = 'ellithy.hr.document'
    _description = 'Employee HR Document'
    _order = 'employee_id, sequence, id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade',
        index=True)
    type_id = fields.Many2one(
        'ellithy.hr.document.type', string='Document Type', required=True,
        ondelete='restrict')
    sequence = fields.Integer(related='type_id.sequence', store=True)
    required = fields.Boolean(related='type_id.required', store=True)

    received = fields.Boolean(string='Received')
    document = fields.Binary(string='File', attachment=True)
    filename = fields.Char(string='Filename')
    received_date = fields.Date(string='Received On')
    expiry_date = fields.Date(string='Expires On')
    note = fields.Char(string='Note')

    legacy_path = fields.Char(
        string='Legacy Path', copy=False,
        help='Relative path held in the legacy column, for file migration.')

    _sql_constraints = [
        ('employee_type_uniq', 'unique(employee_id, type_id)',
         'This document type is already listed for the employee.'),
    ]
