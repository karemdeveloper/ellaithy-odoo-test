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

    # HR letter item 15 -- one set of hours for the whole week, generated
    # into the seven day lines, each of which can still be edited.
    default_from_time = fields.Float(string='Default From', default=9.0)
    default_to_time = fields.Float(string='Default To', default=17.0)
    rest_day = fields.Selection(
        WEEKDAYS, string='Weekly Rest Day', default='4')
    second_rest_day = fields.Selection(
        WEEKDAYS, string='Second Rest Day')
    employee_count = fields.Integer(compute='_compute_employee_count')
    is_company_default = fields.Boolean(
        string='Company Default', compute='_compute_is_company_default')

    def _compute_employee_count(self):
        data = self.env['hr.employee']._read_group(
            [('shift_id', 'in', self.ids)], ['shift_id'], ['__count'])
        counts = {shift.id: count for shift, count in data}
        for shift in self:
            shift.employee_count = counts.get(shift.id, 0)

    def _compute_is_company_default(self):
        defaults = self.env.companies.ibs_default_shift_id
        for shift in self:
            shift.is_company_default = shift in defaults

    @api.constrains('default_from_time', 'default_to_time')
    def _check_default_times(self):
        for shift in self:
            if not (0.0 <= shift.default_from_time < 24.0
                    and 0.0 <= shift.default_to_time < 24.0):
                raise ValidationError(_('Default From and To must be between 00:00 and 23:59.'))
            if shift.default_from_time == shift.default_to_time:
                raise ValidationError(_('Default From and To cannot be equal.'))

    def _week_line_values(self):
        self.ensure_one()
        rest = {self.rest_day, self.second_rest_day} - {False}
        return [{
            'shift_id': self.id, 'day': day,
            'is_off': day in rest,
            'from_time': 0.0 if day in rest else self.default_from_time,
            'to_time': 0.0 if day in rest else self.default_to_time,
        } for day, _label in WEEKDAYS]

    def action_generate_week(self):
        """Write the default hours on all seven days, rest days off.

        Replaces the current day lines; edit any day afterwards for a
        different start, a short day or a flexible day.
        """
        for shift in self:
            shift.line_ids.unlink()
            self.env['ibs.hr.shift.line'].create(shift._week_line_values())
        return True

    @api.model_create_multi
    def create(self, vals_list):
        shifts = super().create(vals_list)
        # A new shift starts with its week filled in, rather than empty.
        for shift, vals in zip(shifts, vals_list):
            if not vals.get('line_ids'):
                shift.action_generate_week()
        return shifts

    def action_assign_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Assign Shift'),
            'res_model': 'ibs.hr.shift.assign.wizard', 'view_mode': 'form',
            'target': 'new', 'context': {'default_shift_id': self.id},
        }

    def action_view_employees(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Employees'),
            'res_model': 'hr.employee', 'view_mode': 'list,form',
            'domain': [('shift_id', '=', self.id)],
        }

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
                ('active', '=', True), '|', ('shift_id', '=', shift.id),
                '&', ('shift_id', '=', False),
                ('company_id.ibs_default_shift_id', '=', shift.id),
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
