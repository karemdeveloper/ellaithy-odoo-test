# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class Training(models.Model):
    _name = 'training.training'
    _description = 'Training'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date_start desc'

    name = fields.Char(string='Reference', required=True, copy=False,
                        readonly=True, default=lambda self: _('New'))

    branch_id = fields.Many2one('ellithy.branch', string='Branch Name', tracking=True)
    department_id = fields.Many2one('hr.department', string='Department', tracking=True)
    employee_ids = fields.Many2many('hr.employee', string='Employees', required=True, tracking=True)
    training_type_id = fields.Many2one('training.type', string='Training Type',
                                        required=True, tracking=True)

    date_start = fields.Date(string='Start Date', required=True, tracking=True)
    date_end = fields.Date(string='End Date', required=True, tracking=True)
    time_start = fields.Float(string='Start Time', widget='float_time')
    time_end = fields.Float(string='End Time', widget='float_time')

    category = fields.Selection([
        ('new_comer', 'New Comer'),
        ('internal', 'Internal'),
        ('external', 'External'),
    ], string='Category', required=True, default='internal', tracking=True)

    cost = fields.Monetary(string='Cost', tracking=True)
    budget = fields.Monetary(string='Budget', tracking=True)
    currency_id = fields.Many2one(
        'res.currency', string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    number_of_hours = fields.Float(string='Number Of Hours')
    description = fields.Html(string='Description')

    trainer_type = fields.Selection([
        ('internal', 'Internal'),
        ('external', 'External'),
    ], string='Trainer Type', default='internal', tracking=True)
    trainer_id = fields.Many2one('training.trainer', string='Trainer', tracking=True)

    certificate_attachment = fields.Binary(string='Certificate Attachment', attachment=True)
    certificate_attachment_filename = fields.Char(string='Certificate Filename')

    training_file_ids = fields.Many2many(
        'ir.attachment',
        'training_training_ir_attachment_rel',
        'training_id',
        'attachment_id',
        string='Training Files',
    )

    active = fields.Boolean(default=True)  # [Claude addition]

    session_ids = fields.One2many(
        'training.session', 'training_id', string='Sessions')
    session_count = fields.Integer(compute='_compute_counts')
    participant_ids = fields.One2many(
        'training.participant', 'training_id', string='Trainees Summary')
    assessment_ids = fields.One2many(
        'training.assessment', 'training_id', string='Assessments')
    assessment_count = fields.Integer(compute='_compute_counts')
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company
    )

    # HR letter item 8 -- the trainees rate the training and the trainer.
    evaluation_survey_id = fields.Many2one(
        'survey.survey', string='Evaluation Form',
        domain=[('is_hr_evaluation', '=', True)],
        default=lambda self: self.env.ref(
            'hr_training_management.survey_training_evaluation',
            raise_if_not_found=False))
    evaluation_auto = fields.Boolean(
        string='Send Evaluation When It Ends', default=True,
        help='Mail every trainee the evaluation link on the day after the '
             'end date.')
    evaluation_sent_at = fields.Datetime(
        string='Evaluation Sent On', readonly=True, copy=False)
    evaluation_progress = fields.Char(
        string='Evaluations Received', compute='_compute_evaluation')
    evaluation_done_count = fields.Integer(compute='_compute_evaluation')
    evaluation_score = fields.Float(
        string='Overall Evaluation (%)', compute='_compute_evaluation',
        digits=(5, 1))
    training_rating = fields.Float(
        string='Training Rating (%)', compute='_compute_evaluation',
        digits=(5, 1))
    trainer_rating = fields.Float(
        string='Trainer Rating (%)', compute='_compute_evaluation',
        digits=(5, 1))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('training.training') or _('New')
        trainings = super().create(vals_list)
        trainings._sync_trainees()
        return trainings

    def write(self, vals):
        result = super().write(vals)
        if 'employee_ids' in vals:
            self._sync_trainees()
        return result

    def _compute_counts(self):
        for training in self:
            training.session_count = len(training.session_ids)
            training.assessment_count = len(training.assessment_ids)

    @api.depends('participant_ids.evaluation_state',
                 'participant_ids.evaluation_score')
    def _compute_evaluation(self):
        for training in self:
            participants = training.participant_ids
            done = participants.filtered(lambda p: p.evaluation_state == 'done')
            training.evaluation_done_count = len(done)
            training.evaluation_progress = '%s / %s' % (len(done), len(participants))
            count = len(done) or 1
            training.evaluation_score = round(sum(done.mapped('evaluation_score')) / count, 1)
            training.training_rating = round(sum(done.mapped('training_rating')) / count, 1)
            training.trainer_rating = round(sum(done.mapped('trainer_rating')) / count, 1)

    def _send_evaluation(self, raise_on_error=False):
        """Mail the evaluation link to every trainee who has not answered."""
        sent = self.browse()
        for training in self:
            problem = False
            if not training.evaluation_survey_id:
                problem = _('Choose an evaluation form first.')
            elif not training.participant_ids:
                problem = _('The training has no trainees.')
            if problem:
                if raise_on_error:
                    raise UserError(problem)
                continue
            skipped = training.participant_ids._send_evaluation(
                training.evaluation_survey_id.sudo())
            training.evaluation_sent_at = fields.Datetime.now()
            if skipped:
                training.message_post(body=_(
                    'Evaluation not sent to %(names)s: no work email on file.',
                    names=', '.join(skipped.employee_id.mapped('name'))))
            sent |= training
        return sent

    def action_send_evaluation(self):
        self._send_evaluation(raise_on_error=True)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {'type': 'success',
                       'message': _('The evaluation link was sent to the trainees.'),
                       'next': {'type': 'ir.actions.act_window_close'}},
        }

    @api.model
    def _cron_send_evaluations(self):
        """Send each finished programme's evaluation once.

        Only programmes that ended in the last ``window`` days are picked
        up, so switching this on does not mail trainees about last year's
        courses. Older ones can still be sent from the form.
        """
        window = int(self.env['ir.config_parameter'].sudo().get_param(
            'hr_training_management.evaluation_window_days', 30))
        today = fields.Date.context_today(self)
        self.search([
            ('evaluation_auto', '=', True), ('evaluation_sent_at', '=', False),
            ('date_end', '<', today),
            ('date_end', '>=', today - timedelta(days=window)),
        ])._send_evaluation()

    def action_view_evaluations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Evaluations'),
            'res_model': 'training.participant', 'view_mode': 'list,pivot',
            'views': [(self.env.ref('hr_training_management.view_training_participant_evaluation_list').id, 'list'),
                      (False, 'pivot')],
            'domain': [('training_id', '=', self.id)],
            'context': {'create': False},
        }

    def _sync_trainees(self):
        """Keep one history line and one attendance line per trainee."""
        Participant = self.env['training.participant']
        for training in self:
            participants = training.participant_ids
            participants.filtered(
                lambda p: p.employee_id not in training.employee_ids).unlink()
            missing = training.employee_ids - participants.employee_id
            if missing:
                Participant.create([{
                    'training_id': training.id, 'employee_id': employee.id,
                } for employee in missing])
            training.session_ids._sync_attendance()

    def action_generate_sessions(self):
        """One session per day of the programme, skipping days that
        already have one. Fridays are skipped; delete any other day the
        programme does not meet."""
        Session = self.env['training.session']
        for training in self:
            if not (training.date_start and training.date_end):
                continue
            taken = set(training.session_ids.mapped('date'))
            day, number = training.date_start, len(training.session_ids)
            vals_list = []
            while day <= training.date_end:
                if day.weekday() != 4 and day not in taken:
                    number += 1
                    vals_list.append({
                        'training_id': training.id,
                        'name': _('Session %(n)s', n=number),
                        'date': day,
                        'time_start': training.time_start,
                        'time_end': training.time_end,
                    })
                day += timedelta(days=1)
            Session.create(vals_list)

    def action_view_sessions(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Sessions'),
            'res_model': 'training.session', 'view_mode': 'list,form',
            'domain': [('training_id', '=', self.id)],
            'context': {'default_training_id': self.id},
        }

    def action_view_assessments(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Assessments'),
            'res_model': 'training.assessment', 'view_mode': 'list,form',
            'domain': [('training_id', '=', self.id)],
            'context': {'default_training_id': self.id},
        }

    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for training in self:
            if training.date_start and training.date_end and training.date_end < training.date_start:
                raise ValidationError(_('End Date cannot be before Start Date.'))

    @api.constrains('time_start', 'time_end')
    def _check_times(self):
        for training in self:
            if training.time_start and training.time_end and training.date_start == training.date_end:
                if training.time_end <= training.time_start:
                    raise ValidationError(_('End Time must be after Start Time on the same day.'))
