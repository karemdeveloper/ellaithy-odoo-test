from odoo import _, api, fields, models
from odoo.exceptions import UserError


class TrainingParticipant(models.Model):
    """One employee on one programme: the line of their training history.

    Kept in step with the programme's trainee list, and carrying the two
    figures HR asked for on the employee file: attendance rate and the
    assessment result.
    """

    _name = 'training.participant'
    _description = 'Training Participant'
    _order = 'date_start desc, id desc'

    training_id = fields.Many2one(
        'training.training', string='Training', required=True, index=True,
        ondelete='cascade')
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='cascade')
    date_start = fields.Date(related='training_id.date_start', store=True)
    date_end = fields.Date(related='training_id.date_end', store=True)
    training_type_id = fields.Many2one(
        related='training_id.training_type_id', store=True)
    trainer_id = fields.Many2one(related='training_id.trainer_id', store=True)
    company_id = fields.Many2one(related='training_id.company_id', store=True)

    session_count = fields.Integer(
        string='Sessions', compute='_compute_attendance', store=True)
    attended_count = fields.Integer(
        string='Attended', compute='_compute_attendance', store=True)
    attendance_rate = fields.Float(
        string='Attendance (%)', compute='_compute_attendance', store=True,
        digits=(5, 1))

    attempt_ids = fields.One2many(
        'training.assessment.attempt', 'participant_id', string='Assessments')
    assessment_score = fields.Float(
        string='Assessment Score', compute='_compute_assessment', store=True,
        digits=(5, 1), help='Best graded score out of 100.')
    assessment_result = fields.Selection(
        [('pending', 'Pending'), ('pass', 'Pass'), ('fail', 'Fail')],
        string='Assessment Result', compute='_compute_assessment', store=True)

    # HR letter item 8 -- the trainee's own rating of the training and the
    # trainer, from the evaluation survey mailed when the programme ends.
    evaluation_input_id = fields.Many2one(
        'survey.user_input', string='Evaluation Answer', readonly=True,
        copy=False, ondelete='set null')
    evaluation_state = fields.Selection(
        [('sent', 'Sent'), ('done', 'Completed')], string='Evaluation',
        readonly=True, copy=False)
    evaluation_score = fields.Float(
        string='Evaluation (%)', readonly=True, copy=False, digits=(5, 1),
        aggregator='avg', help='Overall rating given by the trainee, out of 100.')
    training_rating = fields.Float(
        string='Training Rating (%)', readonly=True, copy=False, digits=(5, 1),
        aggregator='avg')
    trainer_rating = fields.Float(
        string='Trainer Rating (%)', readonly=True, copy=False, digits=(5, 1),
        aggregator='avg')
    evaluation_url = fields.Char(compute='_compute_evaluation_url')

    _sql_constraints = [
        ('training_employee_uniq', 'unique(training_id, employee_id)',
         'This employee is already on the training.'),
    ]

    @api.depends('training_id.session_ids.attendance_ids.status',
                 'training_id.session_ids')
    def _compute_attendance(self):
        for participant in self:
            sessions = participant.training_id.session_ids
            lines = sessions.attendance_ids.filtered(
                lambda a: a.employee_id == participant.employee_id)
            attended = len(lines.filtered(lambda a: a.status == 'present'))
            participant.session_count = len(sessions)
            participant.attended_count = attended
            participant.attendance_rate = (
                100.0 * attended / len(sessions) if sessions else 0.0)

    @api.depends('attempt_ids.state', 'attempt_ids.score',
                 'attempt_ids.result')
    def _compute_assessment(self):
        for participant in self:
            graded = participant.attempt_ids.filtered(
                lambda a: a.state == 'graded')
            if graded:
                best = max(graded, key=lambda a: a.score)
                participant.assessment_score = best.score
                participant.assessment_result = best.result
            else:
                participant.assessment_score = 0.0
                participant.assessment_result = (
                    'pending' if participant.attempt_ids else False)

    def _compute_evaluation_url(self):
        for participant in self:
            answer = participant.sudo().evaluation_input_id
            participant.evaluation_url = (
                '%s%s' % (answer.get_base_url(), answer.get_start_url())
                if answer else False)

    @staticmethod
    def _rating(lines):
        """Scored answers as a percentage of the 5-point maximum."""
        lines = lines.filtered(lambda l: l.question_id.question_type == 'simple_choice'
                               and not l.skipped)
        if not lines:
            return 0.0
        return 100.0 * sum(lines.mapped('answer_score')) / (5.0 * len(lines))

    def _apply_evaluation(self, answer):
        """Copy a completed evaluation onto the trainee's history line."""
        lines = answer.user_input_line_ids
        self.write({
            'evaluation_state': 'done',
            'evaluation_score': round(self._rating(lines), 1),
            'training_rating': round(self._rating(lines.filtered(
                lambda l: l.question_id.training_eval_part == 'training')), 1),
            'trainer_rating': round(self._rating(lines.filtered(
                lambda l: l.question_id.training_eval_part == 'trainer')), 1),
        })
        self.training_id.message_post(body=_(
            'Evaluation received from %(name)s: %(score)s%%.',
            name=self.employee_id.name, score=self.evaluation_score))

    def _send_evaluation(self, survey):
        """Create the trainee's answer token and mail the link.

        Re-sending reuses the open answer, so a lost mail gives back the same
        link. Trainees without a work email are skipped and returned.
        """
        template = self.env.ref(
            'hr_training_management.mail_template_training_evaluation',
            raise_if_not_found=False)
        skipped = self.browse()
        for participant in self.sudo():
            employee = participant.employee_id
            if participant.evaluation_state == 'done':
                continue
            if not employee.work_email:
                skipped |= participant
                continue
            answer = participant.evaluation_input_id
            if not answer or answer.survey_id != survey:
                partner = employee.work_contact_id
                answer = survey._create_answer(
                    partner=partner if partner.email else False,
                    email=employee.work_email, check_attempts=False,
                    training_participant_id=participant.id)
            participant.write({'evaluation_input_id': answer.id,
                               'evaluation_state': 'sent'})
            if template:
                template.send_mail(participant.id, force_send=False)
        return skipped

    def action_view_evaluation(self):
        """The trainee's answers as the printable survey page."""
        self.ensure_one()
        answer = self.sudo().evaluation_input_id
        if not answer:
            raise UserError(_('No evaluation has been sent to this trainee yet.'))
        return {'type': 'ir.actions.act_url', 'target': 'new',
                'url': answer.get_print_url()}
