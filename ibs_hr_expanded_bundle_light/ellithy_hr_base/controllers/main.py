from odoo import http
from odoo.http import request


class EllithyHrPublic(http.Controller):

    @http.route('/ellithy_hr/onboarding_image/<int:company_id>',
                type='http', auth='public', methods=['GET'], readonly=True,
                save_session=False)
    def onboarding_image(self, company_id):
        """Serve the onboarding email image to mail clients.

        A mail client fetches images anonymously, so the image cannot sit
        behind /web/image, which checks the reader's access to the company.
        Only this one field is exposed, and only for an existing company.
        """
        company = request.env['res.company'].sudo().browse(company_id).exists()
        if not company or not company.hr_onboarding_banner:
            raise request.not_found()
        stream = request.env['ir.binary']._get_image_stream_from(
            company, 'hr_onboarding_banner')
        return stream.get_response(max_age=86400)
