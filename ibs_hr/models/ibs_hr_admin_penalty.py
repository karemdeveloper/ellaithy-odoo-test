from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

APPROVAL_STATUS = [
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]


class IbsHrAdminPenalty(models.Model):
    """Administrative penalty catalogue.

    Distinct from the labour-law ladder in ``ibs.hr.violation``: these carry a
    flat cost in currency rather than a number of days, and no escalation.
    """

    _name = 'ibs.hr.admin.penalty'
    _description = 'Administrative Penalty'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    cost = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    active = fields.Boolean(default=True)
    record_ids = fields.One2many(
        'ibs.hr.admin.penalty.record', 'penalty_id', string='Issued')
    record_count = fields.Integer(compute='_compute_record_count')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another administrative penalty already carries this legacy ID.'),
    ]

    def _compute_record_count(self):
        data = self.env['ibs.hr.admin.penalty.record']._read_group(
            [('penalty_id', 'in', self.ids)], ['penalty_id'], ['__count'])
        mapped = {penalty.id: count for penalty, count in data}
        for record in self:
            record.record_count = mapped.get(record.id, 0)


class IbsHrAdminPenaltyRecord(models.Model):
    """One administrative penalty issued to an employee.

    The legacy stores ``penalty_name_snapshot`` and ``cost_snapshot`` beside
    the foreign key, so an issued penalty keeps the wording and price that
    applied on the day even after the catalogue changes. That is deliberate
    and is preserved here.
    """

    _name = 'ibs.hr.admin.penalty.record'
    _description = 'Administrative Penalty Record'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    penalty_id = fields.Many2one(
        'ibs.hr.admin.penalty', string='Penalty', required=True,
        ondelete='restrict', tracking=True)
    giver_id = fields.Many2one(
        'hr.employee', string='Given By', ondelete='restrict')
    date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True)

    name_snapshot = fields.Char(
        string='Penalty (as issued)', readonly=True,
        help='Wording captured when the penalty was issued, so later edits to '
             'the catalogue do not rewrite history.')
    cost_snapshot = fields.Monetary(
        string='Cost (as issued)', readonly=True, currency_field='currency_id')
    custom_cost = fields.Monetary(
        string='Override Cost', currency_field='currency_id',
        help='Set to depart from the catalogue price.')
    amount = fields.Monetary(
        string='Amount', compute='_compute_amount', store=True,
        currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)

    notes = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments')

    approval_status = fields.Selection(
        APPROVAL_STATUS, string='Status', default='pending', required=True,
        tracking=True)
    approved_by = fields.Many2one('res.users', readonly=True)
    approved_at = fields.Datetime(readonly=True)
    rejected_by = fields.Many2one('res.users', readonly=True)
    rejected_at = fields.Datetime(readonly=True)
    rejection_reason = fields.Text()

    payslip_id = fields.Many2one(
        'ibs.hr.payslip', string='Deducted On', readonly=True, copy=False,
        ondelete='set null')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another record already carries this legacy ID.'),
    ]

    @api.depends('cost_snapshot', 'custom_cost')
    def _compute_amount(self):
        for record in self:
            record.amount = record.custom_cost or record.cost_snapshot or 0.0

    @api.onchange('penalty_id')
    def _onchange_penalty_id(self):
        """Take the snapshot at the moment of issue."""
        for record in self:
            if record.penalty_id:
                record.name_snapshot = record.penalty_id.name
                record.cost_snapshot = record.penalty_id.cost

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.admin.penalty.record') or _('New')
            if vals.get('penalty_id') and not vals.get('cost_snapshot'):
                penalty = self.env['ibs.hr.admin.penalty'].browse(
                    vals['penalty_id'])
                vals.setdefault('name_snapshot', penalty.name)
                vals.setdefault('cost_snapshot', penalty.cost)
        return super().create(vals_list)

    def action_approve(self):
        for record in self:
            if record.approval_status != 'pending':
                raise ValidationError(
                    _('Only a pending penalty can be approved.'))
            record.write({
                'approval_status': 'approved',
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
            })

    def action_reject(self):
        for record in self:
            if not record.rejection_reason:
                raise ValidationError(
                    _('Rejecting a penalty requires a reason.'))
            record.write({
                'approval_status': 'rejected',
                'rejected_by': self.env.user.id,
                'rejected_at': fields.Datetime.now(),
            })

    def action_reset(self):
        self.write({'approval_status': 'pending', 'approved_by': False,
                    'approved_at': False, 'rejected_by': False,
                    'rejected_at': False})
