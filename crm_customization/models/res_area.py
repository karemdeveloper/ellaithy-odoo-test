from odoo import models, fields,api

class ResArea(models.Model):
    _name = 'res.area'
    _description = 'Area'
    _rec_name = 'area_name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    area_name = fields.Char(string="Area Name",translate=True)
    branch_area = fields.Many2one('res.branch',string="Branch Name")
