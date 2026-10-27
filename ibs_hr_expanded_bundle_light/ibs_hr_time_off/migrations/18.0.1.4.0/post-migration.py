from odoo import SUPERUSER_ID, api, fields


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    params = env['ir.config_parameter'].sudo()
    if params.get_param('ibs_hr.annual_leave_standard_days') in ('21', '21.0'):
        params.set_param('ibs_hr.annual_leave_standard_days', '14')
    today = fields.Date.context_today(env['ibs.hr.time.off.request'])
    # Replace legacy current-year postings without altering their evidence.
    pairs = set((entry.employee_id.id, entry.type_id.id)
                for entry in env['ibs.hr.time.off.ledger'].search([
                    ('type_id.code', 'in', ('annual', 'casual'))]))
    for employee_id, type_id in pairs:
        if not env['hr.employee'].browse(employee_id).joining_date:
            continue
        env['ibs.hr.time.off.request'].new({
            'employee_id': employee_id, 'type_id': type_id,
            'date_from': today, 'date_to': today,
        })._ensure_entitlements(today)
