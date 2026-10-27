"""Pre-select the five clearance departments named in the requirements.

Finance, Human Resources, Credit, IT and Customer Service sign every exit;
the direct manager is added per leaver by the clearance wizard. Matched by
name on the directorates, so a database without one of them just skips it.
"""
from odoo import SUPERUSER_ID, api

NAMES = ('Finance', 'Human Resources', 'Credit', 'IT', 'Customer Service')


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    departments = env['hr.department'].search([
        ('name', 'in', NAMES), ('dept_type', '=', 'directorate')])
    departments.write({'clearance_default': True})
