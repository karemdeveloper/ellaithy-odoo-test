from odoo import api, fields, models


class CarOrder(models.Model):
    _name = "car.order"
    _description = "Model For Car Order Requests"
    _inherit = "sequence.mixin"
    _sequence_code = "car.order"
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
    # lead_id = fields.Many2one('crm.lead', string="Lead")
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("lead", "Lead"),
        ],
        default="draft",
    )
    """
    def action_open_lead(self):
        self.ensure_one()
        if not self.lead_id:
            return

        return {
            'type': 'ir.actions.act_window',
            'name': 'CRM Lead',
            'res_model': 'crm.lead',
            'view_mode': 'form',
            'res_id': self.lead_id.id,
            'target': 'current',
        }

    def action_create_or_update_lead_state(self):
        self.ensure_one()
        CrmLead = self.env['crm.lead']

        if not self.lead_id:
            # Partner
            Partner = self.env['res.partner']
            partner = Partner.search([('phone', '=', self.phone)], limit=1)
            if not partner:
                partner = Partner.create({
                    'name': f"{self.first_name} {self.last_name}",
                    'phone': self.phone,
                    'email': self.email,
                })

            # Area
            Area = self.env['res.area']
            area = Area.search([('area_name', 'ilike', self.area)], limit=1)
            if not area:
                area = Area.create({'area_name': self.area})

            # Brand
            Brand = self.env['res.brand']
            brand = Brand.search([('brand_name', 'ilike', self.car_brand)], limit=1)
            if not brand:
                brand = Brand.create({'brand_name': self.car_brand})

            # Sub-brand
            SubBrand = self.env['res.sub.brand']
            sub_brand = SubBrand.search([('sub_brand_name', 'ilike', self.car_model)], limit=1)
            if not sub_brand:
                sub_brand = SubBrand.create({
                    'brand_name': brand.id,
                    'sub_brand_name': self.car_model
                })

            # Source
            Source = self.env['res.source']
            source = Source.search([('source_name', 'ilike', 'Website')], limit=1)

            # Call Type
            CallType = self.env['call.type']
            call_type = CallType.search([('name', 'ilike', 'Order Follow-Up')], limit=1)

            # Create Lead
            lead = CrmLead.create({
                'name': f"Opportunity - {partner.name}",
                'partner_id': partner.id,
                'area_name': area.id,
                'brand_name2': [(4, brand.id)],
                'sub_brand_name2': [(4, sub_brand.id)],
                'user_id': self.env.uid,
                'source_name': source.id if source else False,
                'call_type': call_type.id if call_type else False,
                'order_id': self.id,
            })

            # Update Car Order
            self.write({'lead_id': lead.id, 'state': 'lead'})
        else:
            # Lead exists → optionally update state
            self.state = 'lead'
    """
