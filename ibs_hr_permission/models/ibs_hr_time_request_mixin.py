from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_WORKFLOW_TOKEN = object()

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
    _inherit = 'ellithy.hr.action.notification'
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
    company_id = fields.Many2one(
        related='employee_id.company_id', store=True, index=True)

    issue_date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        index=True, tracking=True)

    reasons = fields.Text(string='Reason')
    state = fields.Selection(
        STATE, default='draft', required=True, tracking=True)
    updated_by = fields.Many2one('res.users', string='Updated By', readonly=True)

    def unlink(self):
        if not self.env.su and any(record.state not in ('draft',) for record in self):
            raise ValidationError(_('Only draft documents can be deleted.'))
        return super().unlink()

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
            group = ('ibs_hr_permission.mission_generalist' if self._name == 'ibs.hr.mission'
                     else 'ibs_hr_permission.permission_generalist')
            self._check_request_employee(vals.get('employee_id'), group)
            if not self.env.su and (vals.get('state', 'draft') != 'draft'
                    or any(vals.get(key) for key in ('updated_by', 'checkin_time',
                              'checkout_time', 'checkin_location', 'checkout_location'))):
                raise ValidationError(_('Create a draft request and use the workflow actions.'))
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    self._sequence_code()) or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals:
            group = ('ibs_hr_permission.mission_generalist' if self._name == 'ibs.hr.mission'
                     else 'ibs_hr_permission.permission_generalist')
            self._check_request_employee(vals['employee_id'], group)
        protected = {
            'state', 'updated_by', 'checkin_time', 'checkin_location',
            'checkout_time', 'checkout_location',
        }
        business = {
            'employee_id', 'issue_date', 'reasons', 'permission_type_id',
            'duration_minutes', 'destination', 'custom_hours', 'start_time',
            'end_time',
        }
        if (not self.env.su and protected.intersection(vals)
                and not (self.env.context.get('ibs_request_transition') is _WORKFLOW_TOKEN
                         or self.env.context.get('ibs_mission_capture') is _WORKFLOW_TOKEN)):
            raise ValidationError(_('Use the workflow actions to change status.'))
        if (not self.env.su and business.intersection(vals)
                and any(record.state != 'draft' for record in self)
                and not self.env.context.get('ibs_request_transition') is _WORKFLOW_TOKEN):
            raise ValidationError(_('Return the request to Draft before editing it.'))
        return super().write(vals)

    def _ensure_approval_group(self, xmlid):
        if not self.env.su and not self.env.user.has_group(xmlid):
            raise ValidationError(_('You are not authorized for this approval step.'))

    def _ensure_not_self_approval(self):
        if (not self.env.su and self.env.user.employee_id
                and self.employee_id == self.env.user.employee_id):
            raise ValidationError(_('You cannot approve your own request.'))

    def action_submit(self):
        self.filtered(lambda r: r.state == 'draft').with_context(
            ibs_request_transition=_WORKFLOW_TOKEN).write({'state': 'pending'})
        group = ('ibs_hr_permission.mission_generalist' if self._name == 'ibs.hr.mission'
                 else 'ibs_hr_permission.permission_generalist')
        self._notify_approval_group(group, _('Request awaiting HR approval'))

    def action_approve(self):
        allowed = self._states_awaiting_approval()
        for record in self:
            if record.state not in allowed:
                raise ValidationError(
                    _('Only a pending request can be approved.'))
        self.with_context(ibs_request_transition=_WORKFLOW_TOKEN).write({
            'state': 'approved', 'updated_by': self.env.user.id})
        self._notify_employee(_('Request approved'))

    def action_reject(self):
        if self._name == 'ibs.hr.permission':
            self._ensure_approval_group('ibs_hr_permission.permission_generalist')
            self._ensure_not_self_approval()
            if any(r.state != 'pending' for r in self):
                raise ValidationError(_('Only pending requests can be rejected.'))
        self.with_context(ibs_request_transition=_WORKFLOW_TOKEN).write({
            'state': 'rejected', 'updated_by': self.env.user.id})
        self._notify_employee(_('Request rejected'))

    def action_cancel(self):
        group = ('ibs_hr_permission.mission_admin' if self._name == 'ibs.hr.mission'
                 else 'ibs_hr_permission.permission_generalist')
        for record in self:
            if record.state in ('approved', 'manager_approved'):
                record._ensure_approval_group(group)
        self.with_context(ibs_request_transition=_WORKFLOW_TOKEN).write({
            'state': 'cancelled', 'updated_by': self.env.user.id})
        self._notify_employee(_('Request cancelled'))
        if 'ibs.hr.attendance.day' in self.env:
            for record in self:
                self.env['ibs.hr.attendance.day'].sudo().generate_days(
                    record.issue_date, record.issue_date, record.employee_id)

    def action_reset(self):
        if any(r.state not in ('pending', 'rejected', 'cancelled') for r in self):
            raise ValidationError(_('Only pending, rejected or cancelled requests can be reset.'))
        self.with_context(ibs_request_transition=_WORKFLOW_TOKEN).write({'state': 'draft'})
