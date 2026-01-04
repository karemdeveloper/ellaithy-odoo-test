from odoo import models, fields, api

class ContactUs(models.Model):
    _name = 'contact.us'
    _description = 'Model For Contact Us Messages'
    _inherit = 'sequence.mixin'
    _sequence_code = 'contact.us'
    first_name = fields.Char(string="First Name", required=True,translate=True)
    last_name = fields.Char(string="Last Name", required=True,translate=True)
    email = fields.Char(string="Email", required=True)
    phone = fields.Char(string="Phone", required=True,translate=True)
    area = fields.Char(string="Area", required=True,translate=True)
    message = fields.Text(string="Message",translate=True)


