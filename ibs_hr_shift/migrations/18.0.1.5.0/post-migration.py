from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    employees = env['hr.employee'].search([('shift_id', '!=', False)])
    attendances = env['hr.attendance'].search([
        ('employee_id', 'in', employees.ids),
    ])
    for field_name in (
            'worked_hours', 'overtime_hours', 'validated_overtime_hours',
            'expected_hours'):
        env.add_to_compute(env['hr.attendance']._fields[field_name], attendances)
    attendances._recompute_recordset()
    env['hr.attendance.overtime'].search([
        ('employee_id', 'in', employees.ids),
        ('adjustment', '=', False),
    ]).unlink()
