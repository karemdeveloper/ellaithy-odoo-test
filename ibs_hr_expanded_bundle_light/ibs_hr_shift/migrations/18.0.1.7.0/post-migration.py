import pytz

from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    day_model = env['ibs.hr.attendance.day']
    timezone = day_model._shift_timezone()
    days = day_model.search([('check_in', '!=', False)])
    for day in days:
        local_check_in_date = pytz.UTC.localize(day.check_in).astimezone(
            timezone).date()
        if local_check_in_date != day.date:
            day.write(day._attendance_values(day.employee_id, day.date))
