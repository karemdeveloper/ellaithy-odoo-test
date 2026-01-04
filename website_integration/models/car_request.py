from odoo import fields, models


class CarRequest(models.Model):
    _name = "car.request"
    _description = "Car Request Model"
    _inherit = "sequence.mixin"
    _sequence_code = "car.request"
    first_name = fields.Char(string="First Name", required=True, translate=True)
    last_name = fields.Char(string="Last Name", required=True, translate=True)
    email = fields.Char(string="Email", required=True)
    phone_number = fields.Char(string="Phone Number", required=True, translate=True)
    area = fields.Char(string="Area", required=True, translate=True)
    car_brand = fields.Char(string="Car Brand", required=True, translate=True)
    car_model = fields.Char(string="Car Model", required=True, translate=True)
    car_category = fields.Char(string="Car Category", required=True, translate=True)
    year_of_manufacture = fields.Char(
        string="Year of Manufacture", required=True, translate=True
    )
    message = fields.Text(string="Message", translate=True)
    # lead_id = fields.Many2one("crm.lead", string="Lead")
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
            "type": "ir.actions.act_window",
            "name": "CRM Lead",
            "res_model": "crm.lead",
            "view_mode": "form",
            "res_id": self.lead_id.id,
            "target": "current",
        }

    
    def action_change_to_lead(self):
        self.ensure_one()
        CrmLead = self.env['crm.lead']

        if not self.lead_id:
            # Create a new Lead
            lead_vals = {
                'name': f"Opportunity - {self.first_name} {self.last_name}",
                'partner_id': self.partner_id.id if hasattr(self, 'partner_id') else False,
                'area_name': self.area.id if hasattr(self, 'area') else False,
                'brand_name2': [(4, self.car_brand.id)] if hasattr(self, 'car_brand') else [],
                # 'sub_brand_name2': [(4, self.sub_brand.id)] if hasattr(self, 'sub_brand') else [],
                'user_id': self.env.uid,
                'source_name': self.source.id if hasattr(self, 'source') else False,
                'call_type': self.call_type.id if hasattr(self, 'call_type') else False,
                'request_id': self.id,
            }
            lead = CrmLead.create(lead_vals)

            # Link Lead to Car Request and change state
            self.write({
                'lead_id': lead.id,
                'state': 'lead'
            })
        else:
            # Lead already exists → update its state
            self.lead_id.state = 'lead'

    def action_create_or_update_lead_state(self):
        self.ensure_one()
        CrmLead = self.env['crm.lead']

        if not self.lead_id:
            # Partner
            Partner = self.env['res.partner']
            partner = Partner.search([('phone', '=', self.phone_number)], limit=1)
            if not partner:
                partner = Partner.create({
                    'name': f"{self.first_name} {self.last_name}",
                    'phone': self.phone_number,
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
            call_type = CallType.search([('name', 'ilike', 'Request Follow-Up')], limit=1)

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
                'request_id': self.id,
            })

            # Update Car Request
            self.write({'lead_id': lead.id, 'state': 'lead'})
        else:
            # Lead exists → optionally update state
            self.state = 'lead'
    """
