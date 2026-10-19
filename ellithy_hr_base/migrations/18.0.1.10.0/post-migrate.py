"""Give the existing directorates a sector.

A first mapping by name, for HR to correct on the department form: the
showroom-facing sales teams, the customer-facing service teams, and the back
office. Departments not listed are left empty.
"""
from odoo import SUPERUSER_ID, api

SECTORS = {
    'sales': ('Sales', 'Corporate Sales', 'Used Sales', 'Deposits'),
    'services': ('Customer Service', 'Insurance', 'Credit', 'Papers', 'Movement'),
    'support': ('Finance', 'Human Resources', 'IT', 'Administration', 'Administrative',
                'Board of Directors', 'Executive Secretarial Department',
                'Purchasing', 'Marketing'),
}


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    Department = env['hr.department'].with_context(active_test=False)
    for sector, names in SECTORS.items():
        Department.search([('dept_type', '=', 'directorate'), ('name', 'in', names),
                           ('sector', '=', False)]).write({'sector': sector})
