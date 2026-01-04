from odoo import http
from odoo.http import request
from ..core.security import require_token
import json


class CarRequestAPI(http.Controller):

    @require_token
    @http.route('/api/contact-us/create', type='http', auth='none', methods=['POST'], csrf=False)
    def create(self):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))

            required = ['first_name', 'last_name', 'email', 'phone', 'area']
            for f in required:
                if not data.get(f):
                    return request.make_json_response(
                        {'success': False, 'error': f'Missing {f}'}, status=400
                    )

            record = request.env['contact.us'].create({
                'first_name': data['first_name'],
                'last_name': data['last_name'],
                'email': data['email'],
                'phone': data['phone'],
                'area': data['area'],
                'message': data.get('message', ''),
            })
#
            return request.make_json_response({
                'success': True,
                'id': record.id,
                'message': 'Thank you for contacting Ellaithy Auto Group!',
                'data': record.read([
                    'first_name', 'last_name', 'email', 'phone',
                    'area', 'message', 'create_date'
                ])[0]
            })

        except Exception as e:
            return request.make_json_response({'success': False, 'error': str(e)}, status=500)
