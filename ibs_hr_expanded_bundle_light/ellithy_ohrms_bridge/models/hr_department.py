from odoo import fields, models


class HrDepartment(models.Model):
    _inherit = 'hr.department'

    clearance_notify = fields.Boolean(
        string='Notified When Clearance Completes',
        help="This department's manager is emailed the leaver's details "
             'once every party has signed the clearance.')
    clearance_default = fields.Boolean(
        string='Required for Clearance',
        help='Pre-selected on every new clearance form, so a leaver is sent '
             'to this department automatically. HR can still add or remove '
             'departments per case.')
