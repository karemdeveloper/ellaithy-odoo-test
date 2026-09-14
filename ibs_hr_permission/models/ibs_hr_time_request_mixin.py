from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

STATE = [
    ('draft', 'Draft'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]


class IbsHrTimeRequestMixin(models.AbstractModel):
    """Generic submit/approve/reject/cancel plumbing for a time-off request.

    Only what every such request needs regardless of its business rules: who
    it is for, when it was raised, its approval state and a free-text reason.
    Anything more specific -- duration, type, an admin remark, who referred
    it -- belongs on the concrete model, not here. Permission and Mission
    deliberately end up with a different field set.
    """

    _name = 'ibs.hr.time.request.mixin'
    _description = 'Time Request Mixin'
    _order = 'issue_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True)

    issue_date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        index=True, tracking=True)

    reasons = fields.Text(string='Reason')
    state = fields.Selection(
        STATE, default='draft', required=True, tracking=True)
    updated_by = fields.Many2one('res.users', string='Updated By', readonly=True)

    def _sequence_code(self):
        """Sequence ``code`` used to number a new record of this model."""
        raise NotImplementedError

    def _states_awaiting_approval(self):
        """States ``action_approve()`` may transition to 'approved' from.

        Overridden by Mission, whose HR approval only follows manager
        approval rather than 'pending' directly.
        """
        return ('pending',)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    self._sequence_code()) or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'pending'})

    def action_approve(self):
        allowed = self._states_awaiting_approval()
        for record in self:
            if record.state not in allowed:
                raise ValidationError(
                    _('Only a pending request can be approved.'))
        self.write({'state': 'approved', 'updated_by': self.env.user.id})

    def action_reject(self):
        self.write({'state': 'rejected', 'updated_by': self.env.user.id})

    def action_cancel(self):
        self.write({'state': 'cancelled', 'updated_by': self.env.user.id})

    def action_reset(self):
        self.write({'state': 'draft'})
