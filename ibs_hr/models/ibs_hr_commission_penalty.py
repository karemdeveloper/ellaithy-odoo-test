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
    _inherit = ['mail.thread', 'ellithy.hr.action.notification']
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
    execution_date = fields.Date(
        compute='_compute_execution_date', store=True, readonly=False,
        required=True, tracking=True, precompute=True)
    approval_status = fields.Selection([
        ('pending', 'Pending'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('cancel', 'Cancelled')],
        default='pending', required=True, tracking=True, copy=False)
    reviewed_by = fields.Many2one('res.users', readonly=True, copy=False)
    reviewed_at = fields.Datetime(readonly=True, copy=False)
    rejection_reason = fields.Text(string='Rejection / Cancellation Reason', copy=False)
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another commission penalty already carries this legacy ID.'),
    ]

    @api.depends('date')
    def _compute_execution_date(self):
        for record in self:
            if not record.execution_date:
                record.execution_date = record.date

    def _check_approver(self):
        if not self.env.su and not self.env.user.has_group('ibs_hr.group_ibs_admin_penalty_approver'):
            raise ValidationError(_('Only an Administrative Penalty Approver may review commission penalties.'))

    def action_approve(self):
        return self.write({'approval_status': 'approved'})

    def action_reject(self):
        return self.write({'approval_status': 'rejected'})

    def action_cancel(self):
        return self.write({'approval_status': 'cancel'})

    def action_reset(self):
        return self.write({'approval_status': 'pending'})

    def write(self, vals):
        vals = dict(vals)
        if 'approval_status' in vals:
            self._check_approver()
            target = vals['approval_status']
            allowed = {'approved': ('pending',), 'rejected': ('pending',),
                       'cancel': ('pending', 'approved'), 'pending': ('rejected', 'cancel')}
            for record in self:
                if record.approval_status not in allowed.get(target, ()):
                    raise ValidationError(_('This commission penalty cannot move to that status.'))
                if target in ('rejected', 'cancel') and not (
                        vals.get('rejection_reason', record.rejection_reason) or '').strip():
                    raise ValidationError(_('Rejecting or cancelling a commission penalty requires a reason.'))
            vals.update(reviewed_by=self.env.user.id if target != 'pending' else False,
                        reviewed_at=fields.Datetime.now() if target != 'pending' else False)
        elif {'reviewed_by', 'reviewed_at'} & vals.keys() and not self.env.su:
            raise ValidationError(_('Reviewer details are recorded by the approval actions.'))
        if {'percentage', 'employee_id', 'date', 'execution_date'} & vals.keys():
            if any(r.approval_status != 'pending' for r in self):
                raise ValidationError(_('Reset the commission penalty before changing its terms.'))
        result = super().write(vals)
        if vals.get('approval_status') == 'pending':
            self._notify_approval_group('ibs_hr.group_ibs_admin_penalty_approver', _('Commission penalty awaiting approval'))
        return result

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
            if not self.env.su and (vals.get('approval_status', 'pending') != 'pending'
                                    or vals.get('reviewed_by') or vals.get('reviewed_at')):
                raise ValidationError(_('Create the commission penalty as pending, then submit an approval.'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.commission.penalty') or _('New')
        records = super().create(vals_list)
        records.filtered(lambda r: r.approval_status == 'pending')._notify_approval_group(
            'ibs_hr.group_ibs_admin_penalty_approver', _('Commission penalty awaiting approval'))
        return records
