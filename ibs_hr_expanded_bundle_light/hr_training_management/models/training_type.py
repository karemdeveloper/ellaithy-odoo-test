# -*- coding: utf-8 -*-
from odoo import fields, models


class TrainingType(models.Model):
    _name = 'training.type'
    _description = 'Training Type'
    _order = 'name'

    code = fields.Char(string='Code', required=True)
    name = fields.Char(string='Name', required=True, translate=True)
    active = fields.Boolean(default=True)  # [Claude addition] allows archiving instead of deleting

    _sql_constraints = [
        # [Claude addition] prevents duplicate codes like creating "TECH" twice
        ('code_uniq', 'unique(code)', 'Training Type code must be unique.'),
    ]
