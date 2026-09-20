from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['ibs.hr.overtime'].search([
        ('state', '=', 'draft'), ('candidate_minutes', '<', 31)]).unlink()
