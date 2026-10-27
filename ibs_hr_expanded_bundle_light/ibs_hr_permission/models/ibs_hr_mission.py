from .ibs_hr_time_request_mixin import _WORKFLOW_TOKEN
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def _format_location(latitude, longitude):
    if latitude is None or longitude is None:
        return False
    return '%.6f, %.6f' % (latitude, longitude)


class IbsHrMission(models.Model):
    """Field mission: check in, do the trip, check out, then get approved.

    Kept separate from Permission on purpose: a mission is timed by an
    actual check-in/check-out (with GPS location), optionally overridden by
    a manually entered hour range, and its approval needs a manager to sign
    off before HR does -- none of which Permission has any use for.
    """

    _name = 'ibs.hr.mission'
    _description = 'Mission'
    _inherit = ['ibs.hr.time.request.mixin', 'mail.thread']

    state = fields.Selection(
        selection_add=[('manager_approved', 'HR Generalist Approved')],
        ondelete={'manager_approved': 'cascade'})

    destination = fields.Char(string='Destination', required=True)

    custom_hours = fields.Boolean(
        string='Custom Hours',
        help='Enter a manual From/To time range instead of timing the '
             'mission from check-in to check-out.')
    start_time = fields.Float(string='From', digits=(2, 2))
    end_time = fields.Float(string='To', digits=(2, 2))

    checkin_time = fields.Datetime(string='Check-in Time', readonly=True)
    checkin_location = fields.Char(
        string='Check-in Location', readonly=True,
        help='Latitude, longitude captured at check-in.')
    checkout_time = fields.Datetime(string='Check-out Time', readonly=True)
    checkout_location = fields.Char(
        string='Check-out Location', readonly=True,
        help='Latitude, longitude captured at check-out.')

    duration_hours = fields.Float(
        string='Duration (hours)', compute='_compute_duration', store=True,
        digits=(6, 2))
    admin_remark = fields.Text(string='Admin Remark')

    def _sequence_code(self):
        return 'ibs.hr.mission'

    @api.model
    def _validate_location(self, latitude, longitude):
        if latitude is None or longitude is None:
            raise ValidationError(self.env._(
                'Location is required. Please enable GPS and retry.'))
        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            raise ValidationError(self.env._(
                'The supplied GPS coordinates are invalid.'))
        if (not -90.0 <= latitude <= 90.0
                or not -180.0 <= longitude <= 180.0):
            raise ValidationError(self.env._(
                'The supplied GPS coordinates are invalid.'))
        return latitude, longitude

    def _states_awaiting_approval(self):
        return ('manager_approved',)

    @api.depends('custom_hours', 'start_time', 'end_time',
                 'checkin_time', 'checkout_time')
    def _compute_duration(self):
        for record in self:
            if record.custom_hours:
                record.duration_hours = max(
                    record.end_time - record.start_time, 0.0)
            elif record.checkin_time and record.checkout_time:
                delta = record.checkout_time - record.checkin_time
                record.duration_hours = max(delta.total_seconds() / 3600.0, 0.0)
            else:
                record.duration_hours = 0.0

    @api.constrains('custom_hours', 'start_time', 'end_time')
    def _check_times(self):
        for record in self:
            if not record.custom_hours:
                continue
            for value, label in ((record.start_time, _('start')),
                                 (record.end_time, _('end'))):
                if not 0.0 <= value < 24.0:
                    raise ValidationError(_(
                        'The %(label)s time must fall within the day.',
                        label=label))
            if record.end_time <= record.start_time:
                raise ValidationError(
                    _('The end time must come after the start time.'))

    def action_check_in(self, latitude=None, longitude=None):
        self.ensure_one()
        if (not self.env.su and self.employee_id.user_id != self.env.user
                and not self.env.user.has_group(
                    'ibs_hr_permission.mission_generalist')):
            raise ValidationError(_('Only the employee or HR may check in.'))
        if self.state != 'draft':
            raise ValidationError(_('Only a draft mission can be checked in.'))
        latitude, longitude = self._validate_location(latitude, longitude)
        if self.checkin_time:
            raise ValidationError(_('This mission has already been checked in.'))
        self.with_context(ibs_mission_capture=_WORKFLOW_TOKEN).write({
            'checkin_time': fields.Datetime.now(),
            'checkin_location': _format_location(latitude, longitude),
        })

    def action_check_out(self, latitude=None, longitude=None):
        self.ensure_one()
        if (not self.env.su and self.employee_id.user_id != self.env.user
                and not self.env.user.has_group(
                    'ibs_hr_permission.mission_generalist')):
            raise ValidationError(_('Only the employee or HR may check out.'))
        if self.state != 'draft':
            raise ValidationError(_('Only a draft mission can be checked out.'))
        latitude, longitude = self._validate_location(latitude, longitude)
        if not self.checkin_time:
            raise ValidationError(_('Check in before checking out.'))
        if self.checkout_time:
            raise ValidationError(_('This mission has already been checked out.'))
        self.with_context(ibs_mission_capture=_WORKFLOW_TOKEN).write({
            'checkout_time': fields.Datetime.now(),
            'checkout_location': _format_location(latitude, longitude),
        })

    def action_submit(self):
        for record in self.filtered(lambda r: r.state == 'draft'):
            if not record.checkin_time or not record.checkout_time:
                raise ValidationError(
                    _('Check in and check out with GPS before ending the mission.'))
        return super().action_submit()

    def action_manager_approve(self):
        for record in self:
            record._ensure_approval_group(
                'ibs_hr_permission.mission_generalist')
            record._ensure_not_self_approval()
            if record.state != 'pending':
                raise ValidationError(
                    _('Only a pending mission can be approved by a manager.'))
        self.with_context(ibs_request_transition=_WORKFLOW_TOKEN).write({
            'state': 'manager_approved'})
        self._notify_approval_group('ibs_hr_permission.mission_admin',
                                    _('Mission awaiting HR Admin approval'))

    def action_approve(self):
        for record in self:
            record._ensure_approval_group(
                'ibs_hr_permission.mission_admin')
            record._ensure_not_self_approval()
        result = super().action_approve()
        if 'ibs.hr.attendance.day' in self.env:
            for record in self:
                self.env['ibs.hr.attendance.day'].sudo().generate_days(
                    record.issue_date, record.issue_date, record.employee_id)
        return result

    def action_reject(self):
        for record in self:
            group = ('ibs_hr_permission.mission_admin'
                     if record.state == 'manager_approved'
                     else 'ibs_hr_permission.mission_generalist')
            record._ensure_approval_group(group)
            record._ensure_not_self_approval()
            if record.state not in ('pending', 'manager_approved'):
                raise ValidationError(_('Only missions awaiting approval can be rejected.'))
            if not record.admin_remark:
                raise ValidationError(
                    _('Rejecting a request requires an admin remark.'))
        return super().action_reject()
