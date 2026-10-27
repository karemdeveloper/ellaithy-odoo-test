import uuid

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

TOTAL_MARKS = 100.0


class TrainingAssessment(models.Model):
    """A test for trainees: multiple-choice and essay questions out of 100.

    Multiple-choice answers are marked on submission; essays wait for HR or
    the trainer to mark them, and the attempt is only graded once they have.
    """

    _name = 'training.assessment'
    _description = 'Training Assessment'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'

    name = fields.Char(required=True, tracking=True)
    training_id = fields.Many2one(
        'training.training', string='Training', index=True,
        ondelete='set null', tracking=True)
    description = fields.Html(string='Instructions')
    pass_mark = fields.Float(
        string='Pass Mark', default=70.0, tracking=True,
        help='Score out of 100 needed to pass.')
    question_ids = fields.One2many(
        'training.assessment.question', 'assessment_id', string='Questions',
        copy=True)
    total_marks = fields.Float(
        string='Total Marks', compute='_compute_total_marks', store=True)
    state = fields.Selection(
        [('draft', 'Draft'), ('published', 'Open'), ('closed', 'Closed')],
        default='draft', required=True, tracking=True)
    attempt_ids = fields.One2many(
        'training.assessment.attempt', 'assessment_id', string='Attempts')
    attempt_count = fields.Integer(compute='_compute_attempt_stats')
    pass_count = fields.Integer(compute='_compute_attempt_stats')
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company)

    @api.depends('question_ids.marks')
    def _compute_total_marks(self):
        for assessment in self:
            assessment.total_marks = sum(assessment.question_ids.mapped('marks'))

    def _compute_attempt_stats(self):
        for assessment in self:
            assessment.attempt_count = len(assessment.attempt_ids)
            assessment.pass_count = len(assessment.attempt_ids.filtered(
                lambda a: a.result == 'pass'))

    @api.constrains('pass_mark')
    def _check_pass_mark(self):
        for assessment in self:
            if not 0 < assessment.pass_mark <= TOTAL_MARKS:
                raise ValidationError(_('The pass mark must be between 1 and 100.'))

    def action_publish(self):
        for assessment in self:
            if not assessment.question_ids:
                raise UserError(_('Add questions before opening the assessment.'))
            if round(assessment.total_marks, 2) != TOTAL_MARKS:
                raise UserError(_(
                    'The questions must add up to 100 marks; they add up to '
                    '%(total)s.', total=assessment.total_marks))
            for question in assessment.question_ids.filtered(
                    lambda q: q.question_type == 'mcq'):
                if len(question.option_ids) < 2:
                    raise UserError(_(
                        'Question "%(q)s" needs at least two choices.',
                        q=question.name))
                if len(question.option_ids.filtered('is_correct')) != 1:
                    raise UserError(_(
                        'Question "%(q)s" needs exactly one correct choice.',
                        q=question.name))
        self.write({'state': 'published'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reset_draft(self):
        if self.attempt_ids:
            raise UserError(_(
                'Trainees have already been sent this assessment; close it '
                'instead of editing the questions.'))
        self.write({'state': 'draft'})

    def action_send_to_trainees(self):
        """Create one attempt per trainee and mail each their own link."""
        self.ensure_one()
        if self.state != 'published':
            raise UserError(_('Open the assessment before sending it.'))
        trainees = self.training_id.employee_ids
        if not trainees:
            raise UserError(_('Link the assessment to a training with trainees.'))
        existing = self.attempt_ids.employee_id
        attempts = self.env['training.assessment.attempt'].create([{
            'assessment_id': self.id, 'employee_id': employee.id,
        } for employee in trainees - existing])
        attempts._send_invitation()
        no_mail = attempts.filtered(lambda a: not a.employee_id.work_email)
        message = _('%(count)s trainee(s) invited.', count=len(attempts))
        if no_mail:
            message += ' ' + _('No work email for: %(names)s. Use "Copy link" '
                               'on their attempt or enter their answers here.',
                               names=', '.join(no_mail.employee_id.mapped('name')))
        self.message_post(body=message)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success', 'message': message,
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    def action_view_attempts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Results'),
            'res_model': 'training.assessment.attempt',
            'view_mode': 'list,form',
            'domain': [('assessment_id', '=', self.id)],
            'context': {'default_assessment_id': self.id},
        }


class TrainingAssessmentQuestion(models.Model):
    _name = 'training.assessment.question'
    _description = 'Assessment Question'
    _order = 'assessment_id, sequence, id'

    assessment_id = fields.Many2one(
        'training.assessment', required=True, index=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    question_type = fields.Selection(
        [('mcq', 'Multiple Choice'), ('essay', 'Essay')],
        string='Type', required=True, default='mcq')
    name = fields.Text(string='Question', required=True)
    marks = fields.Float(required=True, default=10.0)
    option_ids = fields.One2many(
        'training.assessment.option', 'question_id', string='Choices', copy=True)

    @api.constrains('marks')
    def _check_marks(self):
        for question in self:
            if question.marks <= 0:
                raise ValidationError(_('Each question must carry marks.'))


class TrainingAssessmentOption(models.Model):
    _name = 'training.assessment.option'
    _description = 'Assessment Choice'
    _order = 'question_id, sequence, id'

    question_id = fields.Many2one(
        'training.assessment.question', required=True, index=True,
        ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Choice', required=True)
    is_correct = fields.Boolean(string='Correct')


class TrainingAssessmentAttempt(models.Model):
    """One trainee taking one assessment.

    The trainee answers through a token link, so no Odoo login is needed.
    HR can also type in the answers of a paper test from the form.
    """

    _name = 'training.assessment.attempt'
    _description = 'Assessment Attempt'
    _inherit = ['mail.thread']
    _order = 'create_date desc, id desc'
    _rec_name = 'employee_id'

    assessment_id = fields.Many2one(
        'training.assessment', required=True, index=True, ondelete='cascade')
    training_id = fields.Many2one(
        related='assessment_id.training_id', store=True, index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Trainee', required=True, index=True,
        ondelete='cascade')
    participant_id = fields.Many2one(
        'training.participant', compute='_compute_participant', store=True,
        index=True)
    access_token = fields.Char(
        copy=False, readonly=True, default=lambda self: uuid.uuid4().hex)
    state = fields.Selection(
        [('draft', 'Not Submitted'), ('submitted', 'Awaiting Marking'),
         ('graded', 'Graded')],
        default='draft', required=True, tracking=True)
    answer_ids = fields.One2many(
        'training.assessment.answer', 'attempt_id', string='Answers')
    auto_score = fields.Float(
        string='Multiple Choice', compute='_compute_scores', store=True)
    manual_score = fields.Float(
        string='Essay', compute='_compute_scores', store=True)
    score = fields.Float(
        string='Score / 100', compute='_compute_scores', store=True,
        tracking=True)
    pass_mark = fields.Float(related='assessment_id.pass_mark')
    result = fields.Selection(
        [('pass', 'Pass'), ('fail', 'Fail')], compute='_compute_result',
        store=True, tracking=True)
    submitted_at = fields.Datetime(readonly=True, copy=False)
    graded_by = fields.Many2one('res.users', readonly=True, copy=False)
    invitation_sent = fields.Boolean(readonly=True, copy=False)

    _sql_constraints = [
        ('assessment_employee_uniq', 'unique(assessment_id, employee_id)',
         'This trainee already has an attempt on the assessment.'),
    ]

    @api.depends('training_id', 'employee_id')
    def _compute_participant(self):
        Participant = self.env['training.participant']
        for attempt in self:
            attempt.participant_id = Participant.search([
                ('training_id', '=', attempt.training_id.id),
                ('employee_id', '=', attempt.employee_id.id),
            ], limit=1) if attempt.training_id else Participant

    @api.depends('answer_ids.marks_awarded')
    def _compute_scores(self):
        for attempt in self:
            mcq = attempt.answer_ids.filtered(lambda a: a.question_type == 'mcq')
            essay = attempt.answer_ids - mcq
            attempt.auto_score = sum(mcq.mapped('marks_awarded'))
            attempt.manual_score = sum(essay.mapped('marks_awarded'))
            attempt.score = attempt.auto_score + attempt.manual_score

    @api.depends('state', 'score', 'assessment_id.pass_mark')
    def _compute_result(self):
        for attempt in self:
            if attempt.state != 'graded':
                attempt.result = False
            else:
                attempt.result = (
                    'pass' if attempt.score >= attempt.assessment_id.pass_mark
                    else 'fail')

    @api.model_create_multi
    def create(self, vals_list):
        attempts = super().create(vals_list)
        attempts._ensure_answer_lines()
        return attempts

    def _ensure_answer_lines(self):
        Answer = self.env['training.assessment.answer']
        for attempt in self:
            missing = attempt.assessment_id.question_ids - attempt.answer_ids.question_id
            if missing:
                Answer.create([{'attempt_id': attempt.id, 'question_id': q.id}
                               for q in missing])

    def get_portal_url(self):
        self.ensure_one()
        return '%s/training/assessment/%s' % (self.get_base_url(), self.access_token)

    def _send_invitation(self):
        template = self.env.ref(
            'hr_training_management.mail_template_assessment_invitation',
            raise_if_not_found=False)
        for attempt in self.filtered(lambda a: a.employee_id.work_email):
            if template:
                template.send_mail(attempt.id, force_send=False)
            attempt.invitation_sent = True

    def action_send_invitation(self):
        self._send_invitation()

    def action_submit(self):
        """Lock the answers, mark the multiple-choice part."""
        for attempt in self:
            if attempt.state != 'draft':
                continue
            attempt.answer_ids._auto_mark()
            has_essay = attempt.answer_ids.filtered(
                lambda a: a.question_type == 'essay')
            attempt.write({
                'state': 'submitted' if has_essay else 'graded',
                'submitted_at': fields.Datetime.now(),
            })

    def action_finish_marking(self):
        for attempt in self:
            if attempt.state != 'submitted':
                raise UserError(_('Only a submitted attempt can be marked.'))
            attempt.write({'state': 'graded', 'graded_by': self.env.user.id})
            attempt.message_post(body=Markup(_(
                'Marked: %(score)s / 100, <b>%(result)s</b>.')) % {
                    'score': round(attempt.score, 1),
                    'result': dict(self._fields['result'].selection)[attempt.result]})

    def action_reopen(self):
        self.write({'state': 'submitted', 'graded_by': False})


class TrainingAssessmentAnswer(models.Model):
    _name = 'training.assessment.answer'
    _description = 'Assessment Answer'
    _order = 'attempt_id, sequence, id'

    attempt_id = fields.Many2one(
        'training.assessment.attempt', required=True, index=True,
        ondelete='cascade')
    question_id = fields.Many2one(
        'training.assessment.question', required=True, ondelete='cascade')
    sequence = fields.Integer(related='question_id.sequence', store=True)
    question_type = fields.Selection(related='question_id.question_type', store=True)
    question_marks = fields.Float(related='question_id.marks', string='Out Of')
    option_id = fields.Many2one(
        'training.assessment.option', string='Chosen Answer',
        domain="[('question_id', '=', question_id)]", ondelete='set null')
    essay_answer = fields.Text(string='Answer')
    is_correct = fields.Boolean(
        compute='_compute_is_correct', store=True)
    marks_awarded = fields.Float(string='Marks')

    @api.depends('option_id.is_correct', 'question_type')
    def _compute_is_correct(self):
        for answer in self:
            answer.is_correct = (answer.question_type == 'mcq'
                                 and answer.option_id.is_correct)

    def _auto_mark(self):
        for answer in self.filtered(lambda a: a.question_type == 'mcq'):
            answer.marks_awarded = (
                answer.question_id.marks if answer.option_id.is_correct else 0.0)

    @api.constrains('marks_awarded')
    def _check_marks_awarded(self):
        for answer in self:
            if not 0 <= answer.marks_awarded <= answer.question_id.marks:
                raise ValidationError(_(
                    'Marks for "%(q)s" must be between 0 and %(max)s.',
                    q=answer.question_id.name, max=answer.question_id.marks))
