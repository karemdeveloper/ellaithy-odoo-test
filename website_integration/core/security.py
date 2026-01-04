import functools
from odoo.http import request
from odoo import fields

def require_token(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.httprequest.headers.get('Authorization', '')
        if not auth.startswith('Bearer '):
            return request.make_json_response(
                {'success': False, 'error': 'Missing or invalid token'}, status=401
            )
        token = auth.split(' ')[1]

        token_rec = request.env['api.token'].sudo().search([
            ('token', '=', token),
            ('expires', '>', fields.Datetime.now())
        ], limit=1)

        if not token_rec:
            return request.make_json_response(
                {'success': False, 'error': 'Invalid or expired token'}, status=401
            )

        # Set user context
        request.update_env(user=token_rec.user_id.id)
        return func(*args, **kwargs)
    return wrapper