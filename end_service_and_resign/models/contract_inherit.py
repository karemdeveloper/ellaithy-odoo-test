from odoo import fields,api,models

class ContractYear(models.Model):
    _inherit = "hr.contract"

    year_contract = fields.Selection([("one","One Year"),("two","Two Year"),("three","Three Year")])