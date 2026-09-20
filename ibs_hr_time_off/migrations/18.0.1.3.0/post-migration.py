from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    annual = env.ref('ibs_hr_time_off.time_off_type_annual')
    if annual.limit_days == 15:
        annual.limit_days = 8
    params = env['ir.config_parameter'].sudo()
    if params.get_param('ibs_hr.annual_leave_first_year_days') in ('15', '15.0'):
        params.set_param('ibs_hr.annual_leave_first_year_days', '8')
    # Reconcile only through the latest already-posted date. Corrections are
    # separate immutable postings; usage and casual grants remain untouched.
    entries = env['ibs.hr.time.off.ledger'].search([
        ('type_id.code', '=', 'annual'), ('entry_type', '=', 'accrual')])
    latest = {}
    for entry in entries:
        pair = (entry.employee_id.id, entry.type_id.id)
        latest[pair] = max(latest.get(pair, entry.date), entry.date)
    for (employee_id, type_id), on_date in latest.items():
        employee = env['hr.employee'].browse(employee_id)
        if not employee.joining_date:
            continue
        # Use the latest posting in the first service year even when subsequent
        # service years have already been posted.
        first_year = entries.filtered(lambda item:
            item.employee_id.id == employee_id and item.type_id.id == type_id)
        request = env['ibs.hr.time.off.request'].new({
            'employee_id': employee_id, 'type_id': type_id,
            'date_from': on_date, 'date_to': on_date})
        first_year = first_year.filtered(
            lambda item: request._service_period(item.date)[2] == 0)
        if first_year:
            request._ensure_entitlements(max(first_year.mapped('date')))
