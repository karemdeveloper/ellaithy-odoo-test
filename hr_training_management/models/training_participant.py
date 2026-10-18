from odoo import api, fields, models


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
