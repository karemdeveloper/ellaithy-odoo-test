from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class IbsHrAttendanceDay(models.Model):
    _inherit = 'ibs.hr.attendance.day'

    state = fields.Selection(
        selection_add=[('no_shift', 'No Shift')],
        ondelete={'no_shift': 'set default'})

    shift_id = fields.Many2one(
        'ibs.hr.shift', string='Shift', readonly=True, ondelete='restrict')
    shift_from = fields.Datetime(string='Shift From', readonly=True)
    shift_to = fields.Datetime(string='Shift To', readonly=True)
    is_flexible_day = fields.Boolean(
        string='Flexible Shift Day', compute='_compute_is_flexible_day',
        help='The shift has no fixed start, so lateness is not measured and '
             'the unachieved hours are what gets deducted.')
    permission_minutes = fields.Integer(
        string='Approved Permission', readonly=True)
    mission_hours = fields.Float(
        string='Approved Mission Hours', readonly=True)


    attendance_count = fields.Integer(compute='_compute_day_record_counts')
    permission_count = fields.Integer(compute='_compute_day_record_counts')
    mission_count = fields.Integer(compute='_compute_day_record_counts')
    time_off_count = fields.Integer(compute='_compute_day_record_counts')
    overtime_count = fields.Integer(compute='_compute_day_record_counts')
    holiday_count = fields.Integer(compute='_compute_day_record_counts')
    rest_credit_count = fields.Integer(compute='_compute_day_record_counts')
    warning_count = fields.Integer(compute='_compute_day_record_counts')

    @api.model
    def _day_attendance_domain(self, employee, work_date):
        # The check-in date owns the complete attendance, even when checkout
        # is on a later date. This keeps one raw attendance in one treatment
        # and prevents it from also appearing on every shift it overlaps.
        return [
            ('employee_id', '=', employee.id),
            ('check_in', '>=', self._utc_datetime(work_date, 0.0)),
            ('check_in', '<', self._utc_datetime(work_date + timedelta(days=1), 0.0))]

    def _day_record_target(self, kind):
        self.ensure_one()
        employee = [('employee_id', '=', self.employee_id.id)]
        targets = {
            'attendance': ('hr.attendance', self._day_attendance_domain(
                self.employee_id, self.date)),
            'permission': ('ibs.hr.permission', employee + [('issue_date', '=', self.date)]),
            'mission': ('ibs.hr.mission', employee + [('issue_date', '=', self.date)]),
            'time_off': ('ibs.hr.time.off.request', employee + [
                ('date_from', '<=', self.date), ('date_to', '>=', self.date)]),
            'overtime': ('ibs.hr.overtime', [('attendance_day_id', '=', self.id),
                                           ('candidate_minutes', '>=', 31)]),
            'holiday': ('ibs.hr.public.holiday', [
                ('date', '=', self.date),
                ('company_id', '=', self.employee_id.company_id.id)]),
            'rest_credit': ('ibs.hr.rest.credit', employee + [('source_date', '=', self.date)]),
            'warning': ('ibs.hr.warning', employee + [('date', '=', self.date)]),
        }
        if kind not in targets:
            raise ValidationError(_('Unknown day record type.'))
        return targets[kind]

    @api.depends('employee_id', 'date', 'shift_id', 'shift_from', 'shift_to')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_day_record_counts(self):
        for day in self:
            for kind in ('attendance', 'permission', 'mission', 'time_off',
                         'overtime', 'holiday', 'rest_credit', 'warning'):
                count = 0
                if day.employee_id and day.date:
                    model, domain = day._day_record_target(kind)
                    if model in self.env and self.env[model].check_access_rights(
                            'read', raise_exception=False):
                        count = self.env[model].search_count(domain)
                day[kind + '_count'] = count

    def action_open_day_records(self, kind=None):
        self.ensure_one()
        kind = kind or self.env.context.get('day_record_kind')
        self.check_access('read')
        model, domain = self._day_record_target(kind)
        if model not in self.env:
            raise ValidationError(_('This feature is not installed.'))
        self.env[model].check_access('read')
        return {
            'type': 'ir.actions.act_window',
            'name': self.env[model]._description,
            'res_model': model, 'view_mode': 'list,form', 'domain': domain,
            'context': dict(self.env.context, create=False),
        }

    @api.depends('check_in', 'check_out', 'employee_id', 'date', 'shift_id',
                 'shift_from', 'shift_to')
    def _compute_worked_hours(self):
        super()._compute_worked_hours()
        for day in self:
            if day.shift_id and day.employee_id and day.date:
                attendances = self.env['hr.attendance'].sudo().search(
                    day._day_attendance_domain(day.employee_id, day.date))
                if attendances:
                    day.worked_hours = self._interval_hours([
                        (attendance.check_in, attendance.check_out)
                        for attendance in attendances.filtered('check_out')])

    @api.depends('shift_id', 'date')
    def _compute_is_flexible_day(self):
        for day in self:
            line = day.shift_id.line_ids.filtered(
                lambda item: day.date and item.day == str(day.date.weekday()))[:1]
            day.is_flexible_day = bool(line and line.is_flexible)

    @api.depends('scheduled_hours', 'worked_hours', 'state',
                 'permission_minutes', 'mission_hours', 'single_punch')
    def _compute_shortfall(self):
        for record in self:
            # A single fingerprint is penalised separately (Finger), so no
            # unachieved hours on top of it.
            if record.state != 'present' or record.single_punch:
                record.shortfall_hours = 0.0
                continue
            covered = (record.worked_hours + record.mission_hours
                       + record.permission_minutes / 60.0)
            record.shortfall_hours = max(record.scheduled_hours - covered, 0.0)

    @api.model
    def _shift_timezone(self):
        tz_name = self.env['ir.config_parameter'].sudo().get_param(
            'ibs_hr_shift.timezone', 'Africa/Cairo')
        return pytz.timezone(tz_name)

    @api.model
    def _utc_datetime(self, work_date, float_hour):
        hour = int(float_hour)
        minute = int(round((float_hour - hour) * 60))
        if minute == 60:
            hour += 1
            minute = 0
        local_value = datetime.combine(work_date, time(hour % 24, minute))
        if hour == 24:
            local_value += timedelta(days=1)
        return self._shift_timezone().localize(local_value).astimezone(
            pytz.UTC).replace(tzinfo=None)

    @api.model
    def _interval_hours(self, intervals):
        intervals = sorted(
            ((start, end) for start, end in intervals
             if start and end and end > start),
            key=lambda item: item[0])
        if not intervals:
            return 0.0
        total = 0.0
        current_start, current_end = intervals[0]
        for start, end in intervals[1:]:
            if start <= current_end:
                current_end = max(current_end, end)
            else:
                total += (current_end - current_start).total_seconds()
                current_start, current_end = start, end
        total += (current_end - current_start).total_seconds()
        return total / 3600.0

    @api.model
    def _shift_values(self, employee, work_date):
        shift = employee.shift_id
        if not shift or work_date < shift.from_date or work_date > shift.to_date:
            return shift, False, False, False
        line = shift.line_ids.filtered(
            lambda item: item.day == str(work_date.weekday()))[:1]
        if not line:
            return shift, False, False, False
        if line.is_off:
            return shift, line, False, False
        if line.is_flexible:
            return (
                shift,
                line,
                self._utc_datetime(work_date, 0.0),
                self._utc_datetime(work_date + timedelta(days=1), 0.0),
            )
        shift_from = self._utc_datetime(work_date, line.from_time)
        end_date = work_date
        if line.to_time <= line.from_time:
            end_date += timedelta(days=1)
        shift_to = self._utc_datetime(end_date, line.to_time)
        return shift, line, shift_from, shift_to

    @api.model
    def _attendance_values(self, employee, work_date):
        shift, line, shift_from, shift_to = self._shift_values(
            employee, work_date)
        active_shift = bool(
            shift and shift.from_date <= work_date <= shift.to_date)
        values = {
            'employee_id': employee.id,
            'date': work_date,
            'shift_id': shift.id if active_shift else False,
            'shift_from': shift_from,
            'shift_to': shift_to,
            'crossed_midnight': bool(
                line and not line.is_flexible and not line.is_off
                and line.to_time <= line.from_time),
            'scheduled_hours': line.number_of_hours if line else 0.0,
            'check_in': False,
            'check_out': False,
            'late_minutes': 0,
            'early_leave_minutes': 0,
            'overtime_hours': 0.0,
            'is_paid_leave': False,
            'permission_minutes': 0,
            'mission_hours': 0.0,
        }

        leave = False
        if 'ibs.hr.time.off.request' in self.env:
            leave = self.env['ibs.hr.time.off.request'].sudo().search([
                ('employee_id', '=', employee.id),
                ('state', '=', 'approved'),
                ('date_from', '<=', work_date),
                ('date_to', '>=', work_date),
            ], limit=1)
        if leave:
            values.update({
                'state': 'leave',
                'is_paid_leave': leave.type_id.paid,
            })

        holiday = self.env['ibs.hr.public.holiday'].sudo().search([
            ('date', '=', work_date),
            ('company_id', '=', employee.company_id.id),
            ('active', '=', True),
        ], limit=1)
        if not leave and holiday:
            values['state'] = 'holiday'
        elif not leave and not active_shift:
            values['state'] = 'no_shift'
        elif not leave and (not line or line.is_off):
            values['state'] = 'weekend'
        elif not leave:
            values['state'] = 'absent'

        # On working days, assign attendance through the employee's expected
        # shift interval rather than grouping fingerprints by calendar date.
        # The checkout of a 20:00-08:00 shift therefore remains on the
        # workday on which that shift started. Off days have no interval, so
        # their optional punches use the local calendar day.
        attendance_domain = self._day_attendance_domain(employee, work_date)
        attendances = self.env['hr.attendance'].sudo().search(
            attendance_domain, order='check_in')
        completed = attendances.filtered('check_out')
        if attendances:
            values.update({
                'check_in': min(attendances.mapped('check_in')),
                'check_out': max(completed.mapped('check_out')) if completed else False,
            })
            if values['state'] == 'absent':
                values['state'] = 'present'
            first_in = values['check_in']
            last_out = values['check_out']
            if shift_from and not line.is_flexible:
                values['late_minutes'] = max(
                    int((first_in - shift_from).total_seconds() // 60), 0)
            if last_out and shift_to and not line.is_flexible:
                values['early_leave_minutes'] = max(
                    int((shift_to - last_out).total_seconds() // 60), 0)
                values['overtime_hours'] = max(
                    (last_out - shift_to).total_seconds() / 3600.0, 0.0)
            elif last_out and line.is_flexible:
                actual_hours = self._interval_hours([
                    (attendance.check_in, attendance.check_out)
                    for attendance in completed])
                values['overtime_hours'] = max(
                    actual_hours - line.number_of_hours, 0.0)

        if 'ibs.hr.mission' in self.env and line and not line.is_off:
            missions = self.env['ibs.hr.mission'].sudo().search([
                ('employee_id', '=', employee.id),
                ('issue_date', '=', work_date),
                ('state', '=', 'approved'),
            ])
            mission_intervals = []
            for mission in missions:
                if mission.custom_hours:
                    mission_date = work_date
                    if values['crossed_midnight'] and mission.start_time < line.from_time:
                        mission_date += timedelta(days=1)
                    start = self._utc_datetime(mission_date, mission.start_time)
                    end = self._utc_datetime(mission_date, mission.end_time)
                else:
                    start, end = mission.checkin_time, mission.checkout_time
                start = max(start, shift_from) if start else False
                end = min(end, shift_to) if end else False
                if start and end and end > start:
                    mission_intervals.append((start, end))
            physical_intervals = [
                (attendance.check_in, attendance.check_out)
                for attendance in completed]
            physical_hours = self._interval_hours(physical_intervals)
            combined_hours = self._interval_hours(
                physical_intervals + mission_intervals)
            values['mission_hours'] = max(
                combined_hours - physical_hours, 0.0)
            if mission_intervals and values['state'] == 'absent':
                values['state'] = 'present'
            if not line.is_flexible:
                # Mission coverage excuses only the part of each boundary gap
                # that was actually covered; permissions apply afterward.
                for field, gap_start, gap_end in (
                        ('late_minutes', shift_from, values['check_in']),
                        ('early_leave_minutes', values['check_out'], shift_to)):
                    if gap_start and gap_end and gap_end > gap_start:
                        covered = self._interval_hours([
                            (max(start, gap_start), min(end, gap_end))
                            for start, end in mission_intervals])
                        values[field] = max(int(
                            (gap_end - gap_start).total_seconds() // 60
                            - covered * 60), 0)
        if 'ibs.hr.permission' in self.env and line and not line.is_off:
            permissions = self.env['ibs.hr.permission'].sudo().search([
                ('employee_id', '=', employee.id),
                ('issue_date', '=', work_date),
                ('state', '=', 'approved'),
            ])
            for permission in permissions:
                allowed = int(permission.duration_minutes)
                if permission.permission_type_id.code == 'lateness':
                    used = min(allowed, values['late_minutes'])
                    values['late_minutes'] -= used
                elif permission.permission_type_id.code == 'early_leave':
                    used = min(allowed, values['early_leave_minutes'])
                    values['early_leave_minutes'] -= used
                else:
                    used = 0
                values['permission_minutes'] += used


        # Pay all complete minutes once 31 minutes are reached.
        minutes = int(values['overtime_hours'] * 60 + 1e-9)
        values['overtime_hours'] = minutes / 60.0 if minutes >= 31 else 0.0
        return values

    @api.model
    def _running_contracts(self, date_from, date_to, employees=None):
        domain = [
            ('state', '=', 'open'),
            ('employee_id.active', '=', True),
            ('date_start', '<=', date_to),
            '|', ('date_end', '=', False), ('date_end', '>=', date_from),
        ]
        if employees:
            domain.append(('employee_id', 'in', employees.ids))
        return self.env['hr.contract'].sudo().search(domain)

    @api.model
    def _apply_automatic_weekends(self, date_from, date_to, employees):
        """Give a shift with no configured rest day one Friday/Saturday off."""
        first_week = date_from - timedelta(days=date_from.weekday())
        last_week = date_to - timedelta(days=date_to.weekday())
        week_starts = []
        current_week = first_week
        while current_week <= last_week:
            week_starts.append(current_week)
            current_week += timedelta(days=7)

        for employee in employees:
            shift = employee.shift_id
            working_days = set(shift.line_ids.mapped('day')) if shift else set()
            if (not shift or len(working_days) < 7
                    or any(shift.line_ids.mapped('is_off'))):
                continue
            weekend_dates = [
                week_start + timedelta(days=weekday)
                for week_start in week_starts for weekday in (4, 5)
            ]
            records = self.search([
                ('employee_id', '=', employee.id),
                ('date', 'in', weekend_dates),
            ])
            records_by_date = {record.date: record for record in records}
            for week_start in week_starts:
                candidates = []
                for weekday in (4, 5):
                    work_date = week_start + timedelta(days=weekday)
                    day = records_by_date.get(work_date)
                    if not day or not (
                            shift.from_date <= work_date <= shift.to_date):
                        continue
                    base_values = self._attendance_values(employee, work_date)
                    day.write(base_values)
                    if base_values['state'] == 'absent':
                        candidates.append(day)
                if candidates:
                    candidates[0].write({
                        'state': 'weekend',
                        'shift_from': False,
                        'shift_to': False,
                        'scheduled_hours': 0.0,
                        'late_minutes': 0,
                        'early_leave_minutes': 0,
                        'overtime_hours': 0.0,
                    })

    @api.model
    def generate_days(self, date_from, date_to, employees=None, contracts=None):
        date_from = fields.Date.to_date(date_from)
        date_to = fields.Date.to_date(date_to)
        if date_to < date_from:
            raise ValidationError(_('To Date must be on or after From Date.'))
        if employees is None:
            contracts = self._running_contracts(date_from, date_to)
            employees = contracts.employee_id
        contract_periods = {}
        for contract in contracts or self.env['hr.contract']:
            contract_periods.setdefault(contract.employee_id.id, []).append((
                contract.date_start, contract.date_end))
        current = date_from
        while current <= date_to:
            for employee in employees:
                if contract_periods and not any(
                        start <= current and (not end or end >= current)
                        for start, end in contract_periods.get(employee.id, [])):
                    continue
                values = self._attendance_values(employee, current)
                existing = self.search([
                    ('employee_id', '=', employee.id),
                    ('date', '=', current),
                ], limit=1)
                if existing:
                    existing.write(values)
                else:
                    self.create(values)
            current += timedelta(days=1)
        self._apply_automatic_weekends(date_from, date_to, employees)
        return True

    @api.model
    def _generate_current_month(self, today=None, employees=None):
        today = fields.Date.to_date(
            today or fields.Date.context_today(self))
        month_start = today.replace(day=1)
        contracts = self._running_contracts(month_start, today, employees)
        employees = contracts.employee_id
        self.generate_days(
            month_start, today, employees=employees, contracts=contracts)
        if 'ibs.hr.overtime' in self.env:
            self.env['ibs.hr.overtime'].generate_from_attendance(
                month_start, today, employees)
        return True

    @api.model
    def _cron_generate_attendance_days(self):
        return self._generate_current_month()
