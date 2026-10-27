from odoo import fields, models


class CallType(models.Model):
    _inherit = "call.type"
    is_website_call_type = fields.Boolean(string="Website Call Type", default=False)
