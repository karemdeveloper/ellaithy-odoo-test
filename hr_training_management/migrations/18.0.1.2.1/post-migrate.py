"""Existing programmes get the training evaluation form (HR letter item 8)."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    survey = env.ref('hr_training_management.survey_training_evaluation',
                     raise_if_not_found=False)
    if survey:
        env['training.training'].with_context(active_test=False).search(
            [('evaluation_survey_id', '=', False)]).write(
            {'evaluation_survey_id': survey.id})
