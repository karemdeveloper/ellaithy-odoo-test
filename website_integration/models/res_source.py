from odoo import fields, models


class ResSource(models.Model):
    _inherit = "res.source"
    is_website_source = fields.Boolean(string="Website Source", default=False)
