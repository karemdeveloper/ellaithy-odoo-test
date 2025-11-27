from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class MailComposer(models.TransientModel):
    _inherit = 'mail.compose.message'

    force_email_from = fields.Char('Force Email From', help='If set, this email_from will be used and never overridden')

    @api.depends('composition_mode', 'email_from', 'model',
                 'res_domain', 'res_ids', 'template_id', 'force_email_from')
    def _compute_authorship(self):
        """Override to respect force_email_from if set"""
        # Store original email_from values before parent compute
        forced_email_from = {composer.id: composer.force_email_from for composer in self if composer.force_email_from}
        
        # Call parent compute
        super()._compute_authorship()
        
        # Restore forced email_from values after parent compute
        for composer in self:
            if composer.id in forced_email_from and forced_email_from[composer.id]:
                composer.email_from = forced_email_from[composer.id]
                _logger.info(f"Composer {composer.id}: Forced email_from to {composer.email_from}")

    def _prepare_mail_values_dynamic(self, res_ids):
        """Override to ensure force_email_from is used in mail values"""
        mail_values_all = super()._prepare_mail_values_dynamic(res_ids)
        
        # If force_email_from is set, override all email_from values
        if self.force_email_from:
            _logger.info(f"Forcing email_from in mail values to: {self.force_email_from}")
            for res_id in res_ids:
                if res_id in mail_values_all:
                    mail_values_all[res_id]['email_from'] = self.force_email_from
                    _logger.info(f"  - Set email_from for res_id {res_id}: {self.force_email_from}")
        
        return mail_values_all

    def _prepare_mail_values_rendered(self, res_ids):
        """Override to ensure force_email_from is used in mail values"""
        mail_values_all = super()._prepare_mail_values_rendered(res_ids)
        
        # If force_email_from is set, override all email_from values
        if self.force_email_from:
            _logger.info(f"Forcing email_from in rendered mail values to: {self.force_email_from}")
            for res_id in res_ids:
                if res_id in mail_values_all:
                    mail_values_all[res_id]['email_from'] = self.force_email_from
                    _logger.info(f"  - Set email_from for res_id {res_id}: {self.force_email_from}")
        
        return mail_values_all
