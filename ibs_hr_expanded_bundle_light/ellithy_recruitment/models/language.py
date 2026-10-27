from odoo import fields, models


class RecruitmentLanguage(models.Model):
    _name = 'ellithy.recruitment.language'
    _description = 'Spoken Language'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
