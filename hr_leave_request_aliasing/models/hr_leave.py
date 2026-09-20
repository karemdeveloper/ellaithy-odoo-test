import re
from datetime import datetime

from odoo import _, api, models
from odoo.exceptions import ValidationError
from odoo.tools import email_split


class TimeOffMailRequest(models.Model):
    _inherit = 'ibs.hr.time.off.request'

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        addresses = email_split(msg_dict.get('email_from', ''))
        if not addresses:
            raise ValidationError(_('The sender has no email address.'))
        sender = addresses[0].lower()
        get = self.env['ir.config_parameter'].sudo().get_param
        prefix = get('hr_holidays.alias_prefix', 'LEAVE REQUEST') or 'LEAVE REQUEST'
        domain = get('hr_holidays.alias_domain', '') or ''
        if not msg_dict.get('subject', '').startswith(prefix):
            raise ValidationError(_('The email subject must start with %s.', prefix))
        if domain and sender.rsplit('@', 1)[-1] != domain.lstrip('@').lower():
            raise ValidationError(_('This sender domain is not allowed.'))
        employees = self.env['hr.employee'].sudo().search([
            '|', ('work_email', '=ilike', sender), ('user_id.email', '=ilike', sender)], limit=2)
        if len(employees) != 1:
            raise ValidationError(_('The sender must match exactly one employee.'))
        employee = employees[0]
        dates = re.findall(r'\d{2}/\d{2}/\d{4}', msg_dict.get('body', ''))
        if not dates:
            raise ValidationError(_('Include dates in DD/MM/YYYY format.'))
        try:
            start = datetime.strptime(dates[0], '%d/%m/%Y').date()
            end = datetime.strptime(dates[1] if len(dates) > 1 else dates[0], '%d/%m/%Y').date()
        except ValueError as error:
            raise ValidationError(_('The email contains an invalid date.')) from error
        kind = self.env['ibs.hr.time.off.type'].sudo().search([
            ('code', '=', 'annual'), ('company_id', '=', employee.company_id.id)], limit=1)
        if not kind:
            raise ValidationError(_('Configure an annual time off type for this company.'))
        values.update(employee_id=employee.id, type_id=kind.id,
                      date_from=start, date_to=end, reason=msg_dict.get('subject', ''))
        # Email creates a draft; submission validates balances and eligibility.
        return super().message_new(msg_dict, values)
