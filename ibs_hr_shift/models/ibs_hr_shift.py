from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


WEEKDAYS = [
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    ('2', 'Wednesday'),
    ('3', 'Thursday'),
    ('4', 'Friday'),
    ('5', 'Saturday'),
    ('6', 'Sunday'),
]


class IbsHrShift(models.Model):
    _name = 'ibs.hr.shift'
    _description = 'Employee Shift'
    _order = 'from_date desc, name'

    name = fields.Char(required=True)
    from_date = fields.Date(string='From Date', required=True)
    to_date = fields.Date(string='To Date', required=True)
    line_ids = fields.One2many(
        'ibs.hr.shift.line', 'shift_id', string='Lines', copy=True)

    @api.constrains('from_date', 'to_date')
    def _check_dates(self):
        for shift in self:
            if shift.from_date and shift.to_date < shift.from_date:
                raise ValidationError(_('To Date must be on or after From Date.'))

    def action_generate_attendance(self):
        if not self.env.su and not self.env.user.has_group('ibs_hr_shift.ibs_hr_shift_generalist'):
            raise ValidationError(_('Only HR Generalists or HR Admins can generate attendance.'))
        today = fields.Date.context_today(self)
        for shift in self:
            employees = self.env['hr.employee'].search([
                ('active', '=', True), ('shift_id', '=', shift.id),
            ])
            date_to = min(shift.to_date, today)
            if shift.from_date <= date_to:
                self.env['ibs.hr.attendance.day'].generate_days(
                    shift.from_date, date_to, employees)
        return True


class IbsHrShiftLine(models.Model):
    _name = 'ibs.hr.shift.line'
    _description = 'Employee Shift Line'
    _order = 'day'

    shift_id = fields.Many2one(
        'ibs.hr.shift', required=True, ondelete='cascade')
    day = fields.Selection(WEEKDAYS, required=True)
    from_time = fields.Float(string='From')
    to_time = fields.Float(string='To')
    number_of_hours = fields.Float(
        string='No. of Hours', compute='_compute_number_of_hours', store=True)
    is_off = fields.Boolean(string='Is Off')
    is_flexible = fields.Boolean(string='Is Flexible')
    flexible_hours = fields.Float(string='Number of Hours')

    _sql_constraints = [
        ('shift_day_unique', 'unique(shift_id, day)',
         'Each day can appear only once in a shift.'),
    ]

    @api.depends('from_time', 'to_time', 'is_off', 'is_flexible',
                 'flexible_hours')
    def _compute_number_of_hours(self):
        for line in self:
            if line.is_off:
                line.number_of_hours = 0.0
            elif line.is_flexible:
                line.number_of_hours = line.flexible_hours
            elif line.from_time or line.to_time:
                duration = line.to_time - line.from_time
                line.number_of_hours = duration if duration > 0 else duration + 24.0
            else:
                line.number_of_hours = 0.0

    @api.constrains('from_time', 'to_time', 'is_off', 'is_flexible',
                    'flexible_hours')
    def _check_hours(self):
        for line in self:
            if line.is_off:
                continue
            if line.is_flexible:
                if not 0.0 < line.flexible_hours <= 24.0:
                    raise ValidationError(_(
                        'Number of Hours must be between zero and 24 for a '
                        'flexible day.'))
                continue
            if not 0.0 <= line.from_time < 24.0:
                raise ValidationError(_('From must be between 00:00 and 23:59.'))
            if not 0.0 <= line.to_time < 24.0:
                raise ValidationError(_('To must be between 00:00 and 23:59.'))
            if line.from_time == line.to_time:
                raise ValidationError(
                    _('From and To cannot be equal on a working day.'))
