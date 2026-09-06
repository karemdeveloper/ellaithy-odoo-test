# -*- coding: utf-8 -*-
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
    company_id = fields.Many2one(
        'res.company', string='Company', default=lambda self: self.env.company
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('training.training') or _('New')
        return super().create(vals_list)

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
