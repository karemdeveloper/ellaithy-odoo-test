from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IbsHrCommissionPenalty(models.Model):
    """A percentage cut applied to an employee's commission.

    Distinct from the other two penalty types: the value is a percentage of
    commission rather than days of pay or a flat cost, so it cannot be
    resolved to an amount until commission for the period is known.
    """

    _name = 'ibs.hr.commission.penalty'
    _description = 'Commission Penalty'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    percentage = fields.Float(
        string='Percentage', digits=(5, 2), required=True, tracking=True,
        help='Share of commission withheld, as a percentage.')
    reason = fields.Char(required=True)
    note = fields.Text()
    date = fields.Date(default=fields.Date.context_today, required=True)
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another commission penalty already carries this legacy ID.'),
    ]

    @api.constrains('percentage')
    def _check_percentage(self):
        for record in self:
            if not 0 < record.percentage <= 100:
                raise ValidationError(_(
                    'A commission penalty must be between 0 and 100 per cent; '
                    'got %(value)s.', value=record.percentage))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.commission.penalty') or _('New')
        return super().create(vals_list)
