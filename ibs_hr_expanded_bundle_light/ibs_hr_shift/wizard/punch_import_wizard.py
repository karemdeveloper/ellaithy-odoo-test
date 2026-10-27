import base64
import csv
import io
import re
from datetime import date, datetime, time, timedelta

import pytz

from odoo import _, fields, models
from odoo.exceptions import UserError

CODE_HEADERS = {
    'employee code', 'code', 'emp code', 'emp no', 'emp no.', 'employee no',
    'employee no.', 'employee id', 'ac-no', 'ac-no.', 'ac no', 'acno',
    'user id', 'userid', 'badge', 'badge id', 'id', 'no', 'no.', 'person id',
    'enroll number', 'enrollnumber', 'كود الموظف', 'الكود', 'رقم الموظف',
}
DATETIME_HEADERS = {
    'datetime', 'date time', 'date/time', 'punch time', 'check time',
    'checktime', 'timestamp', 'punch', 'record time', 'verify time',
    'وقت البصمة', 'التاريخ والوقت',
}
DATE_HEADERS = {'date', 'punch date', 'التاريخ'}
TIME_HEADERS = {'time', 'الوقت'}

DATETIME_FORMATS = (
    '%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S',
    '%Y/%m/%d %H:%M', '%d/%m/%Y %H:%M:%S', '%d/%m/%Y %H:%M',
    '%d-%m-%Y %H:%M:%S', '%d-%m-%Y %H:%M', '%d/%m/%Y %I:%M:%S %p',
    '%d/%m/%Y %I:%M %p', '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
    '%Y-%m-%dT%H:%M:%S',
)
DATE_FORMATS = ('%Y-%m-%d', '%Y/%m/%d', '%d/%m/%Y', '%d-%m-%Y')
TIME_FORMATS = ('%H:%M:%S', '%H:%M', '%I:%M:%S %p', '%I:%M %p')

# A punch this many hours after a night shift's end still belongs to it.
NIGHT_SHIFT_GRACE = timedelta(hours=4)


def _parse(value, formats):
    value = re.sub(r'\s+', ' ', str(value).strip())
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


class IbsHrPunchImportWizard(models.TransientModel):
    """HR letter item 19: load a fingerprint device export.

    One punch per row, as the devices export them. Punches are paired per
    working day into one attendance: first punch in, last punch out. A day
    with a single punch is kept as a single fingerprint so the Finger rule
    applies. Days that already have attendance are left alone.
    """

    _name = 'ibs.hr.punch.import.wizard'
    _description = 'Import Fingerprint Punches'

    file = fields.Binary(string='Device Export (.xlsx or .csv)')
    filename = fields.Char()
    match_by = fields.Selection(
        [('employee_code', 'Employee Code'), ('barcode', 'Badge ID')],
        string='Match Employees By', default='employee_code', required=True)
    regenerate = fields.Boolean(
        string='Recompute Attendance Days', default=True,
        help='Rebuild the attendance days of the imported dates, so '
             'lateness, absence and single fingerprints show at once.')
    state = fields.Selection(
        [('upload', 'Upload'), ('done', 'Done')], default='upload')
    result = fields.Text(readonly=True)

    # ------------------------------------------------------------------
    # Reading the file
    # ------------------------------------------------------------------
    def _rows(self):
        if not self.file:
            raise UserError(_('Choose the device export to upload.'))
        content = base64.b64decode(self.file)
        name = (self.filename or '').lower()
        if name.endswith('.csv') or name.endswith('.txt'):
            text = content.decode('utf-8-sig', errors='replace')
            try:
                dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
            except csv.Error:
                dialect = csv.excel
            return list(csv.reader(io.StringIO(text), dialect))
        try:
            import openpyxl
            book = openpyxl.load_workbook(io.BytesIO(content), read_only=True,
                                          data_only=True)
        except Exception as error:
            raise UserError(_('The file could not be read as Excel or CSV: %s', error))
        sheet = book.worksheets[0]
        return [list(row) for row in sheet.iter_rows(values_only=True)]

    @staticmethod
    def _columns(header):
        names = [re.sub(r'\s+', ' ', str(cell or '').strip().lower()) for cell in header]

        def find(options):
            return next((i for i, name in enumerate(names) if name in options), None)
        code = find(CODE_HEADERS)
        stamp = find(DATETIME_HEADERS)
        day, hour = find(DATE_HEADERS), find(TIME_HEADERS)
        if stamp is None and day is None and hour is not None:
            # ZKTeco-style exports put the whole date-time under "Time".
            stamp, hour = hour, None
        if code is None or (stamp is None and (day is None or hour is None)):
            raise UserError(_(
                'The first row must name the columns: an employee code column '
                '(e.g. "Employee Code", "AC-No.", "User ID") and either a '
                '"Date Time" column or separate "Date" and "Time" columns.'))
        return code, stamp, day, hour

    @staticmethod
    def _code(value):
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip() if value not in (None, '') else ''

    @staticmethod
    def _stamp(row, stamp, day, hour):
        if stamp is not None:
            value = row[stamp] if stamp < len(row) else None
            if isinstance(value, datetime):
                return value
            return _parse(value, DATETIME_FORMATS) if value not in (None, '') else None
        day_value = row[day] if day < len(row) else None
        hour_value = row[hour] if hour < len(row) else None
        if isinstance(day_value, datetime):
            day_value = day_value.date()
        elif day_value not in (None, '') and not isinstance(day_value, date):
            parsed = _parse(day_value, DATE_FORMATS)
            day_value = parsed and parsed.date()
        if isinstance(hour_value, datetime):
            hour_value = hour_value.time()
        elif isinstance(hour_value, float):
            seconds = round(hour_value * 86400)
            hour_value = time(seconds // 3600 % 24, seconds // 60 % 60, seconds % 60)
        elif hour_value not in (None, '') and not isinstance(hour_value, time):
            parsed = _parse(hour_value, TIME_FORMATS)
            hour_value = parsed and parsed.time()
        if not (day_value and hour_value):
            return None
        return datetime.combine(day_value, hour_value)

    def _employee_finder(self):
        Employee = self.env['hr.employee'].with_context(active_test=False)
        cache = {}

        def find(code):
            if code in cache:
                return cache[code]
            field = self.match_by
            employee = Employee.search([(field, '=', code)], limit=2)
            if not employee and field == 'employee_code' and code.isdigit() \
                    and 'employee_code_number' in Employee._fields:
                employee = Employee.search(
                    [('employee_code_number', '=', int(code))], limit=2)
            cache[code] = employee if len(employee) == 1 else Employee
            return cache[code]
        return find

    # ------------------------------------------------------------------
    # Pairing and loading
    # ------------------------------------------------------------------
    def _work_date(self, employee, punch_utc, local_date):
        """The day a punch belongs to: a night shift keeps its morning
        check-out on the day the shift started."""
        Day = self.env['ibs.hr.attendance.day']
        previous = local_date - timedelta(days=1)
        _shift, line, shift_from, shift_to = Day._shift_values(employee, previous)
        if (line and shift_to and not line.is_flexible
                and shift_to.date() > shift_from.date()
                and punch_utc <= shift_to + NIGHT_SHIFT_GRACE):
            return previous
        return local_date

    def action_import(self):
        self.ensure_one()
        Day = self.env['ibs.hr.attendance.day']
        Attendance = self.env['hr.attendance'].sudo()
        timezone = Day._shift_timezone()
        rows = self._rows()
        header_index = next((i for i, row in enumerate(rows)
                             if any(cell not in (None, '') for cell in row)), None)
        if header_index is None:
            raise UserError(_('The file is empty.'))
        code_col, stamp, day_col, hour_col = self._columns(rows[header_index])
        find = self._employee_finder()

        punches, unknown, unreadable = {}, set(), 0
        for row in rows[header_index + 1:]:
            if not any(cell not in (None, '') for cell in row):
                continue
            code = self._code(row[code_col] if code_col < len(row) else None)
            moment = self._stamp(row, stamp, day_col, hour_col)
            if not code or not moment:
                unreadable += 1
                continue
            employee = find(code)
            if not employee:
                unknown.add(code)
                continue
            local = timezone.localize(moment.replace(tzinfo=None))
            punch_utc = local.astimezone(pytz.UTC).replace(tzinfo=None)
            work_date = self._work_date(employee, punch_utc, local.date())
            punches.setdefault((employee, work_date), set()).add(
                punch_utc.replace(microsecond=0))

        created = single = existing = failed = 0
        errors = []
        dates, employees = [], self.env['hr.employee']
        for (employee, work_date), stamps in sorted(
                punches.items(), key=lambda item: (item[0][0].id, item[0][1])):
            stamps = sorted(stamps)
            if Attendance.sudo().search_count(
                    Day._day_attendance_domain(employee, work_date)):
                existing += 1
                continue
            check_in, check_out = stamps[0], stamps[-1]
            try:
                with self.env.cr.savepoint():
                    # One punch: a zero-length attendance, read back by the
                    # attendance day as a single fingerprint.
                    Attendance.create({'employee_id': employee.id,
                                       'check_in': check_in,
                                       'check_out': check_out})
            except Exception as error:
                failed += 1
                if len(errors) < 20:
                    errors.append('%s %s: %s' % (
                        employee.employee_code or employee.name, work_date,
                        str(error).splitlines()[0]))
                continue
            created += 1
            single += len(stamps) == 1 or check_out == check_in
            dates.append(work_date)
            employees |= employee

        if self.regenerate and dates:
            today = fields.Date.context_today(self)
            last = min(max(dates), today)
            if min(dates) <= last:
                Day.generate_days(min(dates), last, employees)

        lines = [
            _('Attendance days created: %(n)s', n=created),
            _('  of which single fingerprint: %(n)s', n=single),
            _('Days skipped, attendance already on file: %(n)s', n=existing),
            _('Employees in the file: %(n)s', n=len(employees)),
        ]
        if dates:
            lines.append(_('Dates: %(start)s to %(end)s', start=min(dates), end=max(dates)))
        if unknown:
            shown = sorted(unknown)[:30]
            lines.append(_('Codes with no matching employee (%(n)s): %(codes)s',
                           n=len(unknown), codes=', '.join(shown)
                           + (' ...' if len(unknown) > 30 else '')))
        if unreadable:
            lines.append(_('Rows without a readable code or date-time: %(n)s', n=unreadable))
        if failed:
            lines.append(_('Days refused (%(n)s):', n=failed))
            lines.extend('  ' + error for error in errors)
        self.write({'state': 'done', 'result': '\n'.join(lines)})
        return {
            'type': 'ir.actions.act_window', 'res_model': self._name,
            'res_id': self.id, 'view_mode': 'form', 'target': 'new',
            'name': _('Import Fingerprint Punches'),
        }

    def action_template(self):
        return {'type': 'ir.actions.act_url', 'target': 'download',
                'url': '/ibs_hr_shift/static/xls/fingerprint_punches_template.xlsx'}
