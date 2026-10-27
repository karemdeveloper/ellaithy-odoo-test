"""Human Resources and Finance are told when a leaver's clearance completes."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['hr.department'].search([
        ('name', 'in', ('Human Resources', 'Finance')),
        ('dept_type', '=', 'directorate')]).write({'clearance_notify': True})
