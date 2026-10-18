from odoo import fields, models


class HrRecruitmentStage(models.Model):
    _inherit = 'hr.recruitment.stage'

    interview_round = fields.Selection(
        [('first', 'First Interview'), ('second', 'Second Interview'),
         ('third', 'Third Interview')],
        string='Interview Round',
        help='Entering this stage asks for an interviewer: if none is '
             'scheduled for this round, the recruiter gets a to-do.')
