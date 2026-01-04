from odoo import http
from odoo.http import request
from odoo.exceptions import AccessDenied, AccessError
import logging

_logger = logging.getLogger(__name__)

class AuthController(http.Controller):

    @http.route("/api/auth/token", methods=["POST"], type="http", auth="none", csrf=False)
    def get_token(self, **post):
        headers = request.httprequest.headers
        db = headers.get("db")
        username = headers.get("username") or headers.get("login")
        password = headers.get("password")

        # Validate
        if not all([db, username, password]):
            return request.make_json_response({
                "success": False,
                "error": "Missing parameters in headers: db, username, password"
            }, status=400)

        try:
            request.session.update(http.get_default_session(), db=db)

            credential = {
                'login': username,
                'password': password,
                'type': 'password'
            }

            # Authenticate
            uid = request.session.authenticate(db, credential)

        except AccessError as e:
            return request.make_json_response({
                "success": False,
                "error": f"Access error: {e.name}"
            }, status=403)
        except AccessDenied:
            return request.make_json_response({
                "success": False,
                "error": "Invalid credentials"
            }, status=401)
        except Exception as e:
            _logger.error(f"Authentication error: {str(e)}")
            return request.make_json_response({
                "success": False,
                "error": "Authentication failed"
            }, status=500)

        if not uid:
            return request.make_json_response({
                "success": False,
                "error": "Authentication failed"
            }, status=401)

        # Generate custom token
        user_id = uid.get('uid') if isinstance(uid, dict) else uid
        access_token = request.env['api.token'].sudo().get_or_create_token(user_id=user_id)

        return request.make_json_response({
            "success": True,
            "access_token": access_token,
            "uid": user_id,
            "company_id": request.env.user.company_id.id,
            "message": "Login successful"
        })