from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ibs_hr_permission_monthly_cap_minutes = fields.Integer(
        string='Monthly Permission Cap (minutes)',
        config_parameter='ibs_hr_permission.monthly_cap_minutes',
        default=240,
        help='Total permission minutes an employee may be granted per '
             'calendar month, across all permission types.')
