from odoo import api, fields, models


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

    # CR 2.4 -- the binary "Received" toggle is replaced by the physical
    # form the HR file actually holds. ``received`` survives as a stored
    # compute so ``document_completeness`` keeps working unchanged.
    copy_type = fields.Selection(
        [('original', 'Original'), ('copy', 'Copy')],
        string='Original / Copy',
        help='Whether the HR file holds the original document or a copy.')
    received = fields.Boolean(
        string='Received', compute='_compute_received', store=True,
        help='A document counts as received once its Original/Copy form is '
             'recorded.')
    document = fields.Binary(string='File', attachment=True)
    filename = fields.Char(string='Filename')
    received_date = fields.Date(string='Received On')
    expiry_date = fields.Date(string='Expires On')
    note = fields.Char(string='Note')

    legacy_path = fields.Char(
        string='Legacy Path', copy=False,
        help='Relative path held in the legacy column, for file migration.')

    @api.depends('copy_type')
    def _compute_received(self):
        for record in self:
            record.received = bool(record.copy_type)

    _sql_constraints = [
        ('employee_type_uniq', 'unique(employee_id, type_id)',
         'This document type is already listed for the employee.'),
    ]
