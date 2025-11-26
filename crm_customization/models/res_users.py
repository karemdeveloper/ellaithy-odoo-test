from odoo import models, fields


class ResUsers(models.Model):
    _inherit = 'res.users'

    branch_id = fields.Many2one('res.branch', string='Branch', help='Branch for complaint access control')

