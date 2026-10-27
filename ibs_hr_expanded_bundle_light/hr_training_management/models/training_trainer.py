# -*- coding: utf-8 -*-
from odoo import fields, models


class TrainingTrainer(models.Model):
    _name = 'training.trainer'
    _description = 'Trainer'
    _order = 'name'

    name = fields.Char(string='Name Of Trainer', required=True)
    training_type_ids = fields.Many2many('training.type', string='Training Type')
    email = fields.Char(string='Email')
    phone = fields.Char(string='Phone')
    field_of_expertise = fields.Char(string='Field Of Expertise')
    address = fields.Text(string='Address')
    active = fields.Boolean(default=True)  # [Claude addition]
    # HR letter item 8 -- the trainer's standing across their programmes.
    trainer_rating = fields.Float(
        string='Average Trainer Rating (%)', compute='_compute_trainer_rating',
        digits=(5, 1))
    evaluation_count = fields.Integer(
        string='Evaluations', compute='_compute_trainer_rating')

    def _compute_trainer_rating(self):
        data = self.env['training.participant']._read_group(
            [('trainer_id', 'in', self.ids), ('evaluation_state', '=', 'done')],
            ['trainer_id'], ['trainer_rating:avg', '__count'])
        ratings = {trainer.id: (rating, count) for trainer, rating, count in data}
        for trainer in self:
            rating, count = ratings.get(trainer.id, (0.0, 0))
            trainer.trainer_rating = round(rating or 0.0, 1)
            trainer.evaluation_count = count

    _sql_constraints = [
        # [Claude addition] avoid duplicate trainer records with same email
        ('email_uniq', 'unique(email)', 'A trainer with this email already exists.'),
    ]
