from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for suffix in ('lateness', 'early_leave'):
        kind = env.ref('ibs_hr_permission.permission_type_' + suffix)
        kind.code = suffix
