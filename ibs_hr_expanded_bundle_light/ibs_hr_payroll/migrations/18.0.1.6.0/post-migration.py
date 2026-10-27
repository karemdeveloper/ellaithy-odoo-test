from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # over_day / over_hour were typed in by hand; they are computed now, and
    # Odoo does not recompute a stored column that already existed.
    env = api.Environment(cr, SUPERUSER_ID, {})
    contracts = env['hr.contract'].with_context(active_test=False).search([])
    for field_name in ('over_day', 'over_hour'):
        env.add_to_compute(env['hr.contract']._fields[field_name], contracts)
    contracts._recompute_recordset()
