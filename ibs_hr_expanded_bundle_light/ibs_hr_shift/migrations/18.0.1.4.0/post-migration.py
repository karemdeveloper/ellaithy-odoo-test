from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    days = env['ibs.hr.attendance.day'].search([])
    for day in days:
        shift = day.employee_id.shift_id
        if shift and shift.from_date <= day.date <= shift.to_date:
            day.write(day._attendance_values(day.employee_id, day.date))
        elif 0 < day.overtime_hours * 60 < 31:
            day.overtime_hours = 0
