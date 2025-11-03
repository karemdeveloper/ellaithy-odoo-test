from odoo import models, fields,api

class ResDepartment(models.Model):
    _name = 'res.department'
    _description = 'Department'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Name")
