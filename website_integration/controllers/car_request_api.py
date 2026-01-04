import json

from odoo import http
from odoo.http import request

from ..core.security import require_token


class CarRequestAPI(http.Controller):

    @require_token
    @http.route(
        "/api/car-request/create",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def create(self):
        try:
            data = json.loads(request.httprequest.data.decode("utf-8"))

            required = [
                "first_name",
                "last_name",
                "email",
                "phone_number",
                "area",
                "car_brand",
                "car_model",
                "car_category",
                "year_of_manufacture",
            ]
            for f in required:
                if not data.get(f):
                    return request.make_json_response(
                        {"success": False, "error": f"Missing {f}"}, status=400
                    )

            record = request.env["car.request"].create(
                {
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "phone_number": data["phone_number"],
                    "area": data["area"],
                    "car_brand": data["car_brand"],
                    "car_model": data["car_model"],
                    "car_category": data["car_category"],
                    "year_of_manufacture": data["year_of_manufacture"],
                    "message": data.get("message", ""),
                }
            )
            """
            # Partner model
            Partner = request.env['res.partner']
            partner = Partner.search([('phone', '=', data['phone_number'])], limit=1)
            if not partner:
                partner = Partner.create({
                    'name': f"{data['first_name']} {data['last_name']}",
                    'phone': data['phone_number'],
                    'email': data['email'],
                })
            # Brand model
            Brand = request.env['res.brand']
            brand = Brand.search([('brand_name', 'ilike', data.get('car_brand'))],limit=1)
            if not brand:
                brand = Brand.create({'brand_name': data.get('car_brand')})
            # Sub-brand model
            Sub_Brand = request.env['res.sub.brand']
            sub_brand = Sub_Brand.search([('sub_brand_name', 'ilike', data.get('car_model'))],limit=1)
            if not sub_brand:
                sub_brand = Sub_Brand.create({
                    'brand_name': brand.id,
                    'sub_brand_name': data.get('car_model')
                })
            # Area model
            Area = request.env['res.area']
            area = Area.search([('area_name', 'ilike', data.get('area'))], limit=1)  # Search area
            if not area:
                area = Area.create({'area_name': data.get('area')})  # Create area if not found
            # Source model
            Source = request.env['res.source']
            source_name = 'Website'  # Static source name
            source = Source.search([('source_name', 'ilike', source_name)], limit=1)
            if not source:
                source = Source.create({'source_name': source_name})
            # Call type model
            CallType = request.env['call.type']
            call_type_name = 'Request Follow-Up'  # Static call type
            call_type = CallType.search([('name', 'ilike', call_type_name)], limit=1)  # Search call type
            if not call_type:
                call_type = CallType.create({'name': call_type_name})
            # Create CRM lead
            lead = request.env['crm.lead'].create({
                'name': f"Opportunity - {partner.name}",
                'partner_id': partner.id,
                'area_name': area.id,
                'brand_name2': [(4, brand.id)],
                'sub_brand_name2': [(4, sub_brand.id)],
                'user_id': request.env.uid,
                'source_name': source.id,
                'call_type': call_type.id,
                'request_id': record.id,
            })
            record.write({'lead_id': lead.id,
                          'state': 'lead',})
            """
            return request.make_json_response(
                {
                    "success": True,
                    "id": record.id,
                    "message": "Car Request created successfully!",
                    "data": record.read(
                        [
                            "first_name",
                            "last_name",
                            "email",
                            "phone_number",
                            "area",
                            "car_brand",
                            "car_model",
                            "car_category",
                            "year_of_manufacture",
                            "message",
                            "create_date",
                        ]
                    )[0],
                }
            )

        except Exception as e:
            return request.make_json_response(
                {"success": False, "error": str(e)}, status=500
            )
