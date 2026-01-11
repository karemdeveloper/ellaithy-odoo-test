from odoo import models, fields

class ResBranch(models.Model):
    _name = 'res.branch'
    _description = 'Branch'
    _rec_name = 'branch_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    branch_name = fields.Char(string="Branch Name",translate=True)
    branch_manager=fields.Many2one('res.users',string='Branch Manager')