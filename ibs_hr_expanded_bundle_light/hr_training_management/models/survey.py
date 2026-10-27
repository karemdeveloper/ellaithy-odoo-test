from odoo import fields, models


class SurveyQuestion(models.Model):
    _inherit = 'survey.question'

    training_eval_part = fields.Selection(
        [('training', 'Training'), ('trainer', 'Trainer')],
        string='Training Evaluation Part',
        help='Which rating a scored answer counts towards on a training '
             'evaluation: the programme itself or the trainer.')


class SurveyUserInput(models.Model):
    """Ties a training evaluation answer to the trainee who gave it."""

    _inherit = 'survey.user_input'

    training_participant_id = fields.Many2one(
        'training.participant', string='Training Participant', index=True,
        ondelete='set null', readonly=True)

    def _mark_done(self):
        result = super()._mark_done()
        for answer in self.sudo().filtered('training_participant_id'):
            answer.training_participant_id._apply_evaluation(answer)
        return result
