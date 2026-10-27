"""Mark the probation survey as an HR evaluation on databases that already
have it: its data block is noupdate, so the new flags do not load there."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    survey = env.ref('ellithy_hr_base.survey_probation_evaluation', raise_if_not_found=False)
    if survey:
        survey.write({
            'is_hr_evaluation': True,
            'is_attempts_limited': True,
            'attempts_limit': 1,
            'description_done': '<p>Thank you. Your evaluation has been saved in the '
                                "employee's file.</p><p dir=\"rtl\">شكرًا لك، تم حفظ "
                                'التقييم في ملف الموظف.</p>',
        })
