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
        selection_add=[('manager_approved', 'Manager Approved')],
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
        if self.checkin_time:
            raise ValidationError(_('This mission has already been checked in.'))
        self.write({
            'checkin_time': fields.Datetime.now(),
            'checkin_location': _format_location(latitude, longitude),
        })

    def action_check_out(self, latitude=None, longitude=None):
        self.ensure_one()
        if not self.checkin_time:
            raise ValidationError(_('Check in before checking out.'))
        if self.checkout_time:
            raise ValidationError(_('This mission has already been checked out.'))
        self.write({
            'checkout_time': fields.Datetime.now(),
            'checkout_location': _format_location(latitude, longitude),
        })

    def action_submit(self):
        for record in self.filtered(lambda r: r.state == 'draft'):
            if record.custom_hours:
                continue
            if not record.checkin_time or not record.checkout_time:
                raise ValidationError(
                    _('Check in and check out before submitting the mission.'))
        return super().action_submit()

    def action_manager_approve(self):
        for record in self:
            if record.state != 'pending':
                raise ValidationError(
                    _('Only a pending mission can be approved by a manager.'))
        self.write({'state': 'manager_approved'})

    def action_reject(self):
        for record in self:
            if not record.admin_remark:
                raise ValidationError(
                    _('Rejecting a request requires an admin remark.'))
        return super().action_reject()
