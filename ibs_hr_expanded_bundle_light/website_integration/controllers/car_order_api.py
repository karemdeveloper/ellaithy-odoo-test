import json

from odoo import http
from odoo.http import request

from ..core.security import require_token


class CarRequestAPI(http.Controller):

    @require_token
    @http.route(
        "/api/car-order/create", type="http", auth="none", methods=["POST"], csrf=False
    )
    def create(self):
        try:
            data = json.loads(request.httprequest.data.decode("utf-8"))

            required = ["first_name", "last_name", "email", "phone"]
            for f in required:
                if not data.get(f):
                    return request.make_json_response(
                        {"success": False, "error": f"Missing {f}"}, status=400
                    )
            # in Car Order Model
            record = request.env["car.order"].create(
                {
                    "car_name": data["car_name"],
                    "first_name": data["first_name"],
                    "last_name": data["last_name"],
                    "email": data["email"],
                    "phone": data["phone"],
                    "area": data["area"],
                    "car_brand": data["car_brand"],
                    "car_model": data["car_model"],
                    "car_category": data["car_category"],
                    "year_of_manufacture": data["year_of_manufacture"],
                    "message": data.get("message", ""),
                }
            )
            # Create Lead
            lead = request.env["lead.mixin"].create_lead_order(record)
            # update state to lead
            record.write({"lead_id": lead.id, "state": "lead"})

            return request.make_json_response(
                {
                    "success": True,
                    "id": record.id,
                    "message": "Car Order created successfully!",
                    "data": record.read(
                        [
                            "car_name",
                            "first_name",
                            "last_name",
                            "email",
                            "phone",
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
