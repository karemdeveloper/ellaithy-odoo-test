"""Give existing trainings their trainee summary lines."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['training.training'].with_context(active_test=False).search([])._sync_trainees()
