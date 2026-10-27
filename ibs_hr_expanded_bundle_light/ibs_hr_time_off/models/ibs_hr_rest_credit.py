from odoo import fields, models


class IbsHrRestCredit(models.Model):
    _name = 'ibs.hr.rest.credit'
    _description = 'Compensatory Rest Credit'
    _order = 'source_date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='cascade')
    source_date = fields.Date(required=True, index=True)
    days = fields.Float(required=True, default=1.0)
    state = fields.Selection([
        ('available', 'Available'),
        ('used', 'Used'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='available')
    request_id = fields.Many2one(
        'ibs.hr.time.off.request', readonly=True, ondelete='restrict')
    attendance_day_id = fields.Many2one(
        'ibs.hr.attendance.day', readonly=True, ondelete='restrict')

    _sql_constraints = [
        ('employee_source_unique', 'unique(employee_id, source_date)',
         'A rest credit already exists for this employee and source date.'),
    ]

