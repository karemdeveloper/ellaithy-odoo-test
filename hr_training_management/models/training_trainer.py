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

    _sql_constraints = [
        # [Claude addition] avoid duplicate trainer records with same email
        ('email_uniq', 'unique(email)', 'A trainer with this email already exists.'),
    ]
