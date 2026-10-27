from odoo import http
from odoo.http import request


class TrainingAssessmentController(http.Controller):
    """The trainee's side of an assessment, reached by a token link.

    Most trainees have no Odoo login, so the attempt's own random token is
    the only credential; everything below runs as superuser on that one
    attempt and nothing else.
    """

    def _attempt(self, token):
        attempt = request.env['training.assessment.attempt'].sudo().search(
            [('access_token', '=', token)], limit=1)
        if not attempt or not token:
            raise request.not_found()
        return attempt

    @http.route('/training/assessment/<string:token>', type='http',
                auth='public', methods=['GET'])
    def assessment_page(self, token, **kwargs):
        attempt = self._attempt(token)
        return request.render('hr_training_management.assessment_page', {
            'attempt': attempt,
            'assessment': attempt.assessment_id,
            'questions': attempt.assessment_id.question_ids,
            'error': kwargs.get('error'),
        })

    @http.route('/training/assessment/<string:token>', type='http',
                auth='public', methods=['POST'])
    def assessment_submit(self, token, **post):
        attempt = self._attempt(token)
        if attempt.state != 'draft' or attempt.assessment_id.state != 'published':
            return request.redirect('/training/assessment/%s' % token)
        missing = []
        for answer in attempt.answer_ids:
            question = answer.question_id
            value = (post.get('q_%s' % question.id) or '').strip()
            if question.question_type == 'mcq':
                option = question.option_ids.filtered(
                    lambda o: str(o.id) == value)
                if not option:
                    missing.append(question)
                answer.option_id = option[:1]
            else:
                if not value:
                    missing.append(question)
                answer.essay_answer = value
        if missing:
            return request.render('hr_training_management.assessment_page', {
                'attempt': attempt,
                'assessment': attempt.assessment_id,
                'questions': attempt.assessment_id.question_ids,
                'error': 'Please answer every question. / برجاء الإجابة على كل الأسئلة.',
                'missing_ids': [q.id for q in missing],
            })
        attempt.action_submit()
        return request.redirect('/training/assessment/%s' % token)
