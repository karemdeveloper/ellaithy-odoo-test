from odoo import models, fields, api

class MailComposeMessage(models.TransientModel):
    _inherit = 'mail.compose.message'
    # field to store selected CC partners
    cc_partners = fields.Many2many(
        'res.partner',
        'mail_compose_message_res_partner_cc_rel',  # relation table
        'wizard_id',  # column referring to wizard
        'partner_id',  # column referring to partner
        string="CC"
    )
    # field to store selected recipient partners
    recipient_partners = fields.Many2many(
        'res.partner',
        'mail_compose_message_res_partner_to_rel',  # relation table
        'wizard_id',  # column referring to wizard
        'partner_id',  # column referring to partner
        string="To"
    )
    # field to store generated CC email addresses
    cc_email = fields.Char(string="CC Emails")
    # method to update cc_email field when cc_partners field changes
    @api.onchange('cc_partners')
    def _onchange_cc_partners(self):
        emails = []
        for partner in self.cc_partners:
            if partner.email:
                emails.append(f'"{partner.name}" <{partner.email}>')
            # else:
            #     emails.append(partner.name)

        self.cc_email = ', '.join(emails)
    # override method to include CC and To partners in mail values
    def _prepare_mail_values(self, res_ids):
        mail_values = super()._prepare_mail_values(res_ids)

        cc_email = self.cc_email
        recipient_ids = self.recipient_partners.ids

        for res_id in res_ids:
            if recipient_ids:
                mail_values[res_id]['recipient_ids'] = [(6, 0, recipient_ids)]
            if cc_email:
                mail_values[res_id]['email_cc'] = cc_email

        return mail_values
