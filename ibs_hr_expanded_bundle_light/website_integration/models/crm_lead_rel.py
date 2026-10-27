from odoo import models, fields


class CrmLeadRel(models.Model):
    _inherit = "crm.lead"
    order_id = fields.Many2one("car.order", string="Order")
    request_id = fields.Many2one("car.request", string="Request")

    def action_open_car_order(self):
        self.ensure_one()

        if not self.order_id:
            return False

        return {
            "name": "Car Order",
            "type": "ir.actions.act_window",
            "res_model": "car.order",
            "view_mode": "form",
            "res_id": self.order_id.id,
            "target": "current",
        }

    def action_open_car_request(self):
        self.ensure_one()

        if not self.request_id:
            return False

        return {
            "name": "Car Request",
            "type": "ir.actions.act_window",
            "res_model": "car.request",
            "view_mode": "form",
            "res_id": self.request_id.id,
            "target": "current",
        }
