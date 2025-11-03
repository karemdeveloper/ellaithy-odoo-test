from odoo import models, fields,api

class ResComplaintType(models.Model):
    _name = 'res.complaint.type'
    _description = 'Complaint Type'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Name")

