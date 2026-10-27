from odoo import http
from odoo.http import request
from ..core.security import require_token
import json


class CarRequestAPI(http.Controller):

    @require_token
    @http.route('/api/instant-approval-request/create', type='http', auth='none', methods=['POST'], csrf=False)
    def create(self):
        try:
            data = json.loads(request.httprequest.data.decode('utf-8'))

            required = ['full_name', 'phone', 'email', 'area',
                        'brand', 'model', 'year', 'payment']
            for f in required:
                if not data.get(f):
                    return request.make_json_response(
                        {'success': False, 'error': f'Missing {f}'}, status=400
                    )

            record = request.env['instant.approval.request'].create({
                'full_name': data.get('full_name'),
                'phone': data.get('phone'),
                'email': data.get('email'),
                'area': data.get('area'),
                'brand': data.get('brand'),
                'model': data.get('model'),
                'year': data.get('year'),
                'payment': data.get('payment'),
                'payment_method': data.get('payment_method'),
                'working_status': data.get('working_status'),
                'home_address': data.get('home_address'),
                'work_address': data.get('work_address'),
                'job_title': data.get('job_title'),
                'deposit_available': data.get('deposit_available'),
                'no_commercial_register_tax_card': data.get('no_commercial_register_tax_card'),
                'qualification': data.get('qualification'),
                'id_card_front': data.get('id_card_front', False),  # expects Base64 image
                'id_card_back': data.get('id_card_back', False),  # expects Base64 image
                'tax_card_front': data.get('tax_card_front'),
                'tax_card_back': data.get('tax_card_back'),
            })

            #
            return request.make_json_response({
                'success': True,
                'id': record.id,
                'message': 'Instant Approval Request created successfully!',
                'data': record.read([
                    'full_name', 'phone', 'email', 'area', 'brand', 'model', 'year',
                    'payment', 'payment_method', 'working_status', 'home_address',
                    'work_address', 'job_title', 'deposit_available',
                    'no_commercial_register_tax_card', 'qualification',
                    'id_card_front', 'id_card_back', 'tax_card_front', 'tax_card_back'
                ])[0]
            })

        except Exception as e:
            return request.make_json_response({'success': False, 'error': str(e)}, status=500)
