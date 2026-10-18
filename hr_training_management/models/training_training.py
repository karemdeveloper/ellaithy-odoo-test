# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


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
