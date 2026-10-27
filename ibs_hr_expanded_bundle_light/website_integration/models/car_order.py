from odoo import api, fields, models


class CarOrder(models.Model):
    _name = "car.order"
    _description = "Model For Car Order Requests"
    _inherit = ["sequence.mixin", "lead.mixin"]
    _sequence_code = "car.order"
    _order = "id desc"
    car_name = fields.Char(string="Car Name", translate=True)
    first_name = fields.Char(string="First Name", required=True, translate=True)
    last_name = fields.Char(string="Last Name", required=True, translate=True)
    email = fields.Char(string="Email", required=True)
    phone = fields.Char(string="Phone", required=True, translate=True)
    area = fields.Char(string="Area", required=True, translate=True)
    car_brand = fields.Char(string="Car Brand", translate=True)
    car_model = fields.Char(string="Car Model", translate=True)
    car_category = fields.Char(string="Car Category", translate=True)
    year_of_manufacture = fields.Char(string="Year of Manufacture", translate=True)
    message = fields.Text(string="Message", translate=True)
    lead_id = fields.Many2one("crm.lead", string="Lead")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("lead", "Lead"),
        ],
        default="draft",
    )

    def action_open_lead(self):
        self.ensure_one()
        if not self.lead_id:
            return

        return {
            "type": "ir.actions.act_window",
            "name": "CRM Lead",
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": self.lead_id.id,
            "target": "current",
        }

    def action_create_or_update_lead_state(self):
        self.ensure_one()
        if not self.lead_id:
            lead = self.env["lead.mixin"].create_lead_order(self)
            # Update Car Order
            self.write({"lead_id": lead.id, "state": "lead"})
        else:
            self.state = "lead"
