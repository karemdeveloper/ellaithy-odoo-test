from odoo import _, fields, models


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    is_hr_evaluation = fields.Boolean(
        string='HR Evaluation',
        help='An evaluation of an employee rather than a quiz: the person '
             'answering is thanked instead of being shown a score, a '
             'pass/fail verdict or a retake button.')


class SurveyUserInput(models.Model):
    """Ties a probation evaluation answer to the employee being evaluated.

    The answering partner is the manager, so the survey alone cannot say who
    the evaluation was about.
    """

    _inherit = 'survey.user_input'

    probation_employee_id = fields.Many2one(
        'hr.employee', string='Evaluated Employee', index=True,
        ondelete='set null', readonly=True)

    def _mark_done(self):
        result = super()._mark_done()
        for answer in self.sudo().filtered('probation_employee_id'):
            employee = answer.probation_employee_id
            employee.message_post(body=_(
                'Probation evaluation completed by %(manager)s: %(score)s%%.',
                manager=answer.nickname or answer.email or _('the manager'),
                score=round(answer.scoring_percentage, 1)))
        return result
