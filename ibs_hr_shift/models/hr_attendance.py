import math

import pytz

from odoo import api, fields, models
from odoo.osv import expression


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    def _custom_shift_records(self):
        return self.filtered(lambda attendance: attendance.employee_id.shift_id)

    @api.depends('employee_id', 'employee_id.shift_id', 'check_in', 'check_out')
    def _compute_worked_hours(self):
        custom = self._custom_shift_records()
        regular = self - custom
        if regular:
            super(HrAttendance, regular)._compute_worked_hours()
        for attendance in custom:
            if attendance.check_in and attendance.check_out:
                attendance.worked_hours = max(
                    (attendance.check_out - attendance.check_in).total_seconds()
                    / 3600.0,
                    0.0,
                )
            else:
                attendance.worked_hours = 0.0

    def _custom_shift_overtime_hours(self):
        self.ensure_one()
        if not (self.check_in and self.check_out and self.employee_id.shift_id):
            return 0.0
        day_model = self.env['ibs.hr.attendance.day']
        timezone = day_model._shift_timezone()
        check_in = fields.Datetime.to_datetime(self.check_in)
        work_date = pytz.UTC.localize(check_in).astimezone(timezone).date()
        shift, line, shift_from, shift_to = day_model._shift_values(
            self.employee_id, work_date)
        holiday = self.env['ibs.hr.public.holiday'].sudo().search_count([
            ('date', '=', work_date),
            ('company_id', '=', self.employee_id.company_id.id),
            ('active', '=', True),
        ])
        if holiday or not line or line.is_off:
            hours = self.worked_hours
        elif line.is_flexible:
            hours = max(self.worked_hours - line.number_of_hours, 0.0)
        else:
            hours = max(
                (self.check_out - shift_to).total_seconds() / 3600.0,
                0.0,
            )
        minutes = math.floor(max(hours, 0.0) * 60.0 + 1e-9)
        return minutes / 60.0 if minutes >= 31 else 0.0

    @api.depends('employee_id', 'employee_id.shift_id', 'check_in', 'check_out',
                 'worked_hours')
    def _compute_overtime_hours(self):
        custom = self._custom_shift_records()
        regular = self - custom
        if regular:
            super(HrAttendance, regular)._compute_overtime_hours()
        for attendance in custom:
            attendance.overtime_hours = attendance._custom_shift_overtime_hours()

    @api.depends('employee_id', 'employee_id.shift_id', 'overtime_status',
                 'overtime_hours')
    def _compute_validated_overtime_hours(self):
        custom = self._custom_shift_records()
        regular = self - custom
        if regular:
            super(HrAttendance, regular)._compute_validated_overtime_hours()
        for attendance in custom:
            attendance.validated_overtime_hours = (
                max(attendance.overtime_hours, 0.0)
                if attendance.overtime_status != 'refused' else 0.0)

    def _update_overtime(self, employee_attendance_dates=None):
        employee_attendance_dates = (
            employee_attendance_dates or self._get_attendances_dates())
        regular_dates = {
            employee: dates
            for employee, dates in employee_attendance_dates.items()
            if not employee.shift_id
        }
        result = (super()._update_overtime(regular_dates)
                  if regular_dates else None)

        # Custom shifts are the sole overtime source for assigned employees.
        # Remove Odoo working-schedule rows, which may contain negative hours.
        custom_domain = expression.FALSE_DOMAIN
        for employee, dates in employee_attendance_dates.items():
            if employee.shift_id:
                custom_domain = expression.OR([custom_domain, [
                    ('employee_id', '=', employee.id),
                    ('date', 'in', [item[1] for item in dates]),
                    ('adjustment', '=', False),
                ]])
        if custom_domain != expression.FALSE_DOMAIN:
            self.env['hr.attendance.overtime'].sudo().search(
                custom_domain).unlink()
        return result
