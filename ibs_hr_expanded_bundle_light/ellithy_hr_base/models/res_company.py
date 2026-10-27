from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    hr_onboarding_banner = fields.Image(
        string='Onboarding Email Image', max_width=1200, max_height=1200,
        help='Shown at the top of the onboarding (welcome) email, under the '
             'company logo band. Best at 1200 px wide.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    hr_onboarding_banner = fields.Image(
        related='company_id.hr_onboarding_banner', readonly=False)
