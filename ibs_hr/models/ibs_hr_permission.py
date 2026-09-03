from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# The legacy keeps both in `time_leaves`, told apart by `flag`. Which value
# means which is not documented, but the data settles it: flag=0 carries a
# destination on 90% of rows and averages 9.5 hours, flag=1 rarely carries one
# and averages 4 hours. A mission is a trip somewhere; a permission is a few
# hours away from the desk.
KIND = [
    ('permission', 'Permission'),
    ('mission', 'Mission'),
]
LEGACY_FLAG = {'mission': 0, 'permission': 1}

STATE = [
    ('draft', 'Draft'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancelled', 'Cancelled'),
]


class IbsHrPermission(models.Model):
    """Hourly permission or field mission.

    One model rather than two: the legacy holds both in a single table with
    identical columns, and splitting them would duplicate the approval
    workflow for no gain. The menus filter by ``kind``.
    """

    _name = 'ibs.hr.permission'
    _description = 'Permission / Mission'
    _inherit = ['mail.thread']
    _order = 'issue_date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    kind = fields.Selection(
        KIND, string='Type', required=True, default='permission', index=True,
        tracking=True)
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
    start_time = fields.Float(string='From', required=True, digits=(2, 2))
    end_time = fields.Float(string='To', required=True, digits=(2, 2))
    duration_hours = fields.Float(
        string='Duration (hours)', compute='_compute_duration', store=True,
        digits=(6, 2))

    # Mission-only
    destination = fields.Char(
        string='Destination',
        help='Legacy column "distny" -- where the employee was sent.')
    location = fields.Char(
        string='GPS Location',
        help='Latitude, longitude captured at check-in.')

    reasons = fields.Text(string='Reason')
    admin_remark = fields.Text(string='Admin Remark')
    state = fields.Selection(
        STATE, default='draft', required=True, tracking=True)
    referred_by = fields.Many2one('hr.employee', string='Referred By')
    updated_by = fields.Many2one('res.users', string='Updated By', readonly=True)

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another request already carries this legacy ID.'),
    ]

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        for record in self:
            record.duration_hours = max(record.end_time - record.start_time, 0.0)

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        for record in self:
            for value, label in ((record.start_time, _('start')),
                                 (record.end_time, _('end'))):
                if not 0.0 <= value < 24.0:
                    raise ValidationError(_(
                        'The %(label)s time must fall within the day.',
                        label=label))
            if record.end_time <= record.start_time:
                raise ValidationError(
                    _('The end time must come after the start time.'))

    @api.constrains('kind', 'destination')
    def _check_mission_destination(self):
        for record in self:
            if record.kind == 'mission' and not record.destination:
                raise ValidationError(
                    _('A mission needs a destination.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                code = ('ibs.hr.mission' if vals.get('kind') == 'mission'
                        else 'ibs.hr.permission')
                vals['name'] = self.env['ir.sequence'].next_by_code(code) or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'pending'})

    def action_approve(self):
        for record in self:
            if record.state != 'pending':
                raise ValidationError(
                    _('Only a pending request can be approved.'))
        self.write({'state': 'approved', 'updated_by': self.env.user.id})

    def action_reject(self):
        for record in self:
            if not record.admin_remark:
                raise ValidationError(
                    _('Rejecting a request requires an admin remark.'))
        self.write({'state': 'rejected', 'updated_by': self.env.user.id})

    def action_cancel(self):
        self.write({'state': 'cancelled', 'updated_by': self.env.user.id})

    def action_reset(self):
        self.write({'state': 'draft'})
