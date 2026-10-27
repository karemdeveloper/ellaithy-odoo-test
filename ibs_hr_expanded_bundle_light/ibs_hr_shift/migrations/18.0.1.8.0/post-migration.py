from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    days = env['ibs.hr.attendance.day'].search([])
    for day in days:
        day.write(day._attendance_values(day.employee_id, day.date))
