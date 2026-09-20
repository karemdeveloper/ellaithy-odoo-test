from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for suffix in ('casual', 'annual', 'birthday', 'public_holiday', 'compensatory_rest'):
        kind = env.ref('ibs_hr_time_off.time_off_type_' + suffix)
        if kind.approval_route == 'both':
            kind.approval_route = 'hr'
    annual = env.ref('ibs_hr_time_off.time_off_type_annual')
    if annual.limit_days == 8:
        annual.limit_days = 15
    # Historical posted grants remain as audit evidence; HR can adjust them.
