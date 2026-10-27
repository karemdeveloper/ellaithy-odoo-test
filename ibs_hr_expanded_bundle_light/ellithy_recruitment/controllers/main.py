import base64
import re

from odoo import _, http
from odoo.http import request

# Where an application came from, by the ``src`` parameter of the link.
SOURCES = {
    'link': 'ellithy_recruitment.utm_source_job_link',
    'qr': 'ellithy_recruitment.utm_source_qr_code',
}
MAX_CV_BYTES = 5 * 1024 * 1024
CV_TYPES = ('.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png')


class EllithyCareers(http.Controller):
    """Public job application pages, without the website app.

    One page lists the open jobs; each job has its own link (for ads) and a
    QR code (for branch posters and walk-ins) leading to the same form.
    Submitting creates the candidate and the application, so it lands in
    the recruitment pipeline straight away.
    """

    def _open_jobs(self):
        return request.env['hr.job'].sudo().search(
            [('online_apply', '=', True), ('active', '=', True)], order='name')

    @http.route('/careers', type='http', auth='public', methods=['GET'], sitemap=False)
    def careers(self, **kwargs):
        return request.render('ellithy_recruitment.careers_list', {
            'jobs': self._open_jobs(),
            'company': request.env.company.sudo(),
        })

    @http.route('/careers/<int:job_id>', type='http', auth='public',
                methods=['GET'], sitemap=False)
    def apply_form(self, job_id, src='link', **kwargs):
        job = self._open_jobs().filtered(lambda j: j.id == job_id)
        if not job:
            raise request.not_found()
        return request.render('ellithy_recruitment.careers_apply', self._form_values(job, src, {}, {}))

    def _form_values(self, job, src, values, errors):
        env = request.env
        return {
            'job': job,
            'src': src if src in SOURCES else 'link',
            'values': values,
            'errors': errors,
            'degrees': env['hr.recruitment.degree'].sudo().search([]),
            'languages': env['ellithy.recruitment.language'].sudo().search([]),
            'marital': env['hr.candidate']._fields['marital_status'].selection,
            'military': env['hr.candidate']._fields['military_status'].selection,
            'company': env.company.sudo(),
        }

    @http.route('/careers/<int:job_id>', type='http', auth='public',
                methods=['POST'], sitemap=False)
    def apply_submit(self, job_id, **post):
        job = self._open_jobs().filtered(lambda j: j.id == job_id)
        if not job:
            raise request.not_found()
        src = post.get('src') if post.get('src') in SOURCES else 'link'
        # Bots fill every field; people never see this one.
        if post.get('website_url'):
            return request.redirect('/careers')

        values = {k: (v.strip() if isinstance(v, str) else v) for k, v in post.items()}
        errors = {}
        for field in ('name', 'phone', 'national_id'):
            if not values.get(field):
                errors[field] = _('Required')
        if values.get('national_id') and not re.fullmatch(r'\d{14}', values['national_id']):
            errors['national_id'] = _('Must be 14 digits')
        if values.get('email') and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', values['email']):
            errors['email'] = _('Not a valid email')
        cv = request.httprequest.files.get('cv')
        cv_data = cv.read() if cv and cv.filename else b''
        if cv_data and (len(cv_data) > MAX_CV_BYTES or not cv.filename.lower().endswith(CV_TYPES)):
            errors['cv'] = _('PDF, Word or image, up to 5 MB')
        if errors:
            return request.render('ellithy_recruitment.careers_apply',
                                  self._form_values(job, src, values, errors))

        env = request.env(su=True)
        Candidate = env['hr.candidate']
        candidate = Candidate.search(
            [('national_id', '=', values['national_id'])], limit=1)
        candidate_vals = {
            'partner_name': values['name'],
            'email_from': values.get('email') or False,
            'partner_phone': values['phone'],
            'national_id': values['national_id'],
            'birthdate': values.get('birthdate') or False,
            'marital_status': values.get('marital_status') or False,
            'military_status': values.get('military_status') or False,
            'previous_job_title': values.get('previous_job_title') or False,
            'previous_experience_years': float(values.get('experience_years') or 0),
            'previous_experience': values.get('previous_experience') or False,
            'notice_period_days': int(values.get('notice_period_days') or 0),
            'type_id': int(values['degree_id']) if (values.get('degree_id') or '').isdigit() else False,
            'language_ids': [(6, 0, [int(i) for i in request.httprequest.form.getlist('language_ids') if i.isdigit()])],
            'company_id': job.company_id.id or env.company.id,
        }
        if candidate:
            candidate.write({k: v for k, v in candidate_vals.items() if v})
        else:
            candidate = Candidate.create(candidate_vals)
        source = env.ref(SOURCES[src], raise_if_not_found=False)
        applicant = env['hr.applicant'].create({
            'candidate_id': candidate.id,
            'job_id': job.id,
            'source_id': source.id if source else False,
            'company_id': job.company_id.id or env.company.id,
        })
        if cv_data:
            env['ir.attachment'].create({
                'name': cv.filename,
                'datas': base64.b64encode(cv_data),
                'res_model': 'hr.applicant',
                'res_id': applicant.id,
            })
        applicant.message_post(body=_('Application received from the %(src)s.',
                                      src=_('QR code') if src == 'qr' else _('job link')))
        return request.render('ellithy_recruitment.careers_thanks', {
            'job': job, 'applicant': applicant, 'candidate': candidate,
            'company': env.company,
        })
