from odoo import _, api, fields, models

ROUNDS = [
    ('phone', 'Phone Screen'),
    ('first', 'First Interview'),
    ('second', 'Second Interview'),
    ('third', 'Third Interview'),
]

RATING = [
    ('1', '1 - Poor'),
    ('2', '2 - Below expectations'),
    ('3', '3 - Meets expectations'),
    ('4', '4 - Good'),
    ('5', '5 - Excellent'),
]


class InterviewQuestion(models.Model):
    """A question asked of every applicant to a job of this grade."""

    _name = 'ellithy.interview.question'
    _description = 'Interview Question'
    _order = 'grade_id, sequence, id'

    grade_id = fields.Many2one(
        'ellithy.hr.grade', string='Job Grade', required=True, index=True,
        ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Question', required=True, translate=True)
    active = fields.Boolean(default=True)


class ApplicantEvaluation(models.Model):
    """One interviewer's scored evaluation of one interview round."""

    _name = 'ellithy.applicant.evaluation'
    _description = 'Interview Evaluation'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    applicant_id = fields.Many2one(
        'hr.applicant', string='Application', required=True, index=True,
        ondelete='cascade')
    candidate_id = fields.Many2one(
        related='applicant_id.candidate_id', store=True)
    job_id = fields.Many2one(related='applicant_id.job_id', store=True)
    interview_round = fields.Selection(
        ROUNDS, string='Round', required=True, default='first')
    interviewer_id = fields.Many2one(
        'hr.employee', string='Interviewer', required=True,
        default=lambda self: self.env.user.employee_id)
    date = fields.Date(default=fields.Date.context_today, required=True)
    line_ids = fields.One2many(
        'ellithy.applicant.evaluation.line', 'evaluation_id', string='Questions')
    score = fields.Float(
        string='Score (%)', compute='_compute_score', store=True, digits=(5, 1),
        help='Average rating across the questions, as a percentage of 5.')
    recommendation = fields.Selection(
        [('hire', 'Hire'), ('next_round', 'Next round'), ('maybe', 'Maybe'),
         ('other_job', 'Maybe for another job'), ('reject', 'Reject')],
        string='Recommendation', tracking=True)
    notes = fields.Text(string='Interview Notes')
    state = fields.Selection(
        [('draft', 'Draft'), ('done', 'Submitted')], default='draft',
        tracking=True)

    @api.depends('line_ids.rating')
    def _compute_score(self):
        for evaluation in self:
            rated = evaluation.line_ids.filtered('rating')
            evaluation.score = (
                100.0 * sum(int(line.rating) for line in rated) / (5 * len(rated))
                if rated else 0.0)

    @api.depends('applicant_id', 'interview_round', 'interviewer_id')
    def _compute_display_name(self):
        rounds = dict(ROUNDS)
        for evaluation in self:
            evaluation.display_name = '%s - %s (%s)' % (
                evaluation.applicant_id.partner_name or '',
                rounds.get(evaluation.interview_round, ''),
                evaluation.interviewer_id.name or '')

    def action_submit(self):
        for evaluation in self:
            evaluation.state = 'done'
            evaluation.applicant_id.message_post(body=_(
                '%(round)s evaluated by %(who)s: %(score)s%%, %(rec)s.',
                round=dict(ROUNDS)[evaluation.interview_round],
                who=evaluation.interviewer_id.name,
                score=round(evaluation.score, 1),
                rec=dict(self._fields['recommendation'].selection).get(
                    evaluation.recommendation, '-')))

    def action_reset(self):
        self.write({'state': 'draft'})


class ApplicantEvaluationLine(models.Model):
    _name = 'ellithy.applicant.evaluation.line'
    _description = 'Interview Evaluation Line'
    _order = 'evaluation_id, sequence, id'

    evaluation_id = fields.Many2one(
        'ellithy.applicant.evaluation', required=True, index=True,
        ondelete='cascade')
    sequence = fields.Integer(default=10)
    question = fields.Char(required=True)
    rating = fields.Selection(RATING, string='Rating')
    comment = fields.Char()
