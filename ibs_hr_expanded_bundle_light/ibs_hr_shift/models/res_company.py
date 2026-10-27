from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    ibs_default_shift_id = fields.Many2one(
        'ibs.hr.shift', string='Default Shift',
        help='Used for every employee of the company who has no shift of '
             'their own: attendance days, lateness and leave day counts.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    ibs_default_shift_id = fields.Many2one(
        related='company_id.ibs_default_shift_id', readonly=False)
