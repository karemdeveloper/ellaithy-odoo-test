from odoo import models, fields, api


class MailActivity(models.Model):
    _inherit = 'mail.activity'

    # Override the date_deadline field to include time
    date_deadline = fields.Datetime(
        string='Due Date',
        required=True,
        index=True,
        default=fields.Datetime.now
    )

