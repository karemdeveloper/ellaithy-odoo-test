import base64

from odoo import api, fields, models


class HrJob(models.Model):
    _inherit = 'hr.job'

    grade_id = fields.Many2one(
        'ellithy.hr.grade', string='Job Grade', ondelete='restrict',
        help='Picks the interview questions used to evaluate applicants for '
             'this job.')
    online_apply = fields.Boolean(
        string='Accept Online Applications', default=True,
        help='Publishes the application page for this job. Its link and QR '
             'code can go on job ads and branch posters.')
    apply_url = fields.Char(
        string='Application Link', compute='_compute_apply_url')
    apply_qr = fields.Binary(
        string='Application QR Code', compute='_compute_apply_url')
    interview_question_count = fields.Integer(
        compute='_compute_interview_question_count')

    @api.depends('online_apply')
    def _compute_apply_url(self):
        report = self.env['ir.actions.report']
        for job in self:
            if not job.id or not job.online_apply:
                job.apply_url = False
                job.apply_qr = False
                continue
            job.apply_url = '%s/careers/%s' % (job.get_base_url(), job.id)
            png = report.barcode('QR', job.apply_url + '?src=qr', width=300, height=300)
            job.apply_qr = base64.b64encode(png)

    @api.depends('grade_id')
    def _compute_interview_question_count(self):
        for job in self:
            job.interview_question_count = len(job.grade_id.interview_question_ids)

    def _interview_questions(self):
        self.ensure_one()
        return self.grade_id.interview_question_ids.filtered('active')


class EllithyHrGrade(models.Model):
    _inherit = 'ellithy.hr.grade'

    interview_question_ids = fields.One2many(
        'ellithy.interview.question', 'grade_id', string='Interview Questions')
