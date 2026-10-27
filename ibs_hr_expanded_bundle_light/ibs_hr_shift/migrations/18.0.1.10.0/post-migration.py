from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    day_model = env['ibs.hr.attendance.day']
    employees = env['hr.employee'].search([('shift_id', '!=', False)])
    for employee in employees:
        days = day_model.search([('employee_id', '=', employee.id)])
        if days:
            day_model._apply_automatic_weekends(
                min(days.mapped('date')), max(days.mapped('date')), employee)
