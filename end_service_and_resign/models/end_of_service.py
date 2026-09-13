from odoo import  fields,api,models


class EndService(models.Model):
    _name = 'end.service'
    _inherit = 'end.rewards'
    _description = "End service"
    _rec_name = "employee_id"

