from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

CAP_PARAM = 'ibs_hr_permission.monthly_cap_minutes'
DEFAULT_CAP_MINUTES = 240  # 4 hours

DURATION_MINUTES = [
    ('30', '30 Minutes'),
    ('60', '60 Minutes'),
    ('90', '90 Minutes'),
    ('120', '120 Minutes'),
]


class IbsHrPermission(models.Model):
    """Hourly permission request: lateness or early leave.

    Deliberately not modelled with free start/end times like a mission --
    the business only ever grants one of four fixed durations, so the field
    is a dropdown rather than a computed difference. The monthly total and
    the yesterday/today/tomorrow date window are both enforced here, because
    both are Permission-specific rules that Mission has no equivalent of.
    """

    _name = 'ibs.hr.permission'
    _description = 'Permission'
    _inherit = ['ibs.hr.time.request.mixin', 'mail.thread']

    permission_type_id = fields.Many2one(
        'ibs.hr.permission.type', string='Permission Type', required=True,
        tracking=True)
    duration_minutes = fields.Selection(
        DURATION_MINUTES, string='Duration', required=True, default='30',
        tracking=True)
    duration_hours = fields.Float(
        string='Duration (hours)', compute='_compute_duration_hours',
        store=True, digits=(6, 2))

    @api.depends('duration_minutes')
    def _compute_duration_hours(self):
        for record in self:
            record.duration_hours = (
                int(record.duration_minutes) / 60.0
                if record.duration_minutes else 0.0)

    def _sequence_code(self):
        return 'ibs.hr.permission'

    @api.constrains('issue_date')
    def _check_date_window(self):
        for record in self:
            if record.env.user.has_group('ellithy_hr_base.group_ellithy_hr_admin'):
                continue
            today = fields.Date.context_today(record)
            allowed = (today - timedelta(days=1), today, today + timedelta(days=1))
            if record.issue_date not in allowed:
                raise ValidationError(_(
                    'The permission date must be yesterday, today or '
                    'tomorrow.'))

    @api.constrains('employee_id', 'issue_date', 'duration_minutes', 'state')
    def _check_monthly_cap(self):
        cap = int(self.env['ir.config_parameter'].sudo().get_param(
            CAP_PARAM, default=DEFAULT_CAP_MINUTES))
        checked = set()
        for record in self:
            key = (record.employee_id.id, record.issue_date.year,
                   record.issue_date.month)
            if not record.employee_id or record.issue_date is None or key in checked:
                continue
            checked.add(key)
            month_start = record.issue_date.replace(day=1)
            month_end = month_start + relativedelta(months=1, days=-1)
            siblings = self.search([
                ('employee_id', '=', record.employee_id.id),
                ('issue_date', '>=', month_start),
                ('issue_date', '<=', month_end),
                ('state', '!=', 'cancelled'),
            ])
            total = sum(int(sibling.duration_minutes) for sibling in siblings)
            if total > cap:
                raise ValidationError(_(
                    'This request brings %(employee)s\'s permissions for '
                    '%(month)s to %(total)s minutes, over the %(cap)s-minute '
                    'monthly cap.',
                    employee=record.employee_id.name,
                    month=month_start.strftime('%B %Y'),
                    total=total, cap=cap))
