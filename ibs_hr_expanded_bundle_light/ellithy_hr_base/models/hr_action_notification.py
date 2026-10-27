from markupsafe import Markup

from odoo import _, models
from odoo.exceptions import AccessError


class HrActionNotification(models.AbstractModel):
    _name = 'ellithy.hr.action.notification'
    _description = 'HR action email routing'

    def _check_request_employee(self, employee_id, generalist_group):
        if self.env.su:
            return
        employee = self.env['hr.employee'].sudo().browse(employee_id)
        if employee and employee.company_id not in self.env.companies:
            raise AccessError(_('The employee must belong to an authorized company.'))
        if (not self.env.user.has_group(generalist_group)
                and (not employee or employee.user_id != self.env.user)):
            raise AccessError(_('You may only create or edit requests for your own employee.'))

    def _notify_employee(self, stage):
        for record in self:
            employee = record.sudo().employee_id
            email = employee.work_email or employee.user_id.email
            if email:
                self.env['mail.mail'].sudo().create({
                    'subject': _('%(stage)s: %(record)s', stage=stage,
                                 record=record.display_name),
                    'email_to': email,
                    'email_from': employee.company_id.email or self.env.user.email_formatted or self.env.ref('base.user_admin').email_formatted,
                    'body_html': Markup('<p>%s</p><p>%s</p>') % (stage, record.display_name),
                    'model': record._name, 'res_id': record.id,
                    'auto_delete': False,
                })

    def _notify_approval_group(self, group_xmlid, stage):
        group = self.env.ref(group_xmlid)
        for record in self:
            company = record.sudo().employee_id.company_id
            recipients = set()
            for user in group.sudo().users.filtered(
                    lambda u: u.active and not u.share and u.email
                    and company in u.company_ids):
                try:
                    record.with_user(user).check_access('read')
                except AccessError:
                    continue
                recipients.add(user.email)
            if not recipients:
                record.sudo().message_post(
                    author_id=self.env.user.partner_id.id,
                    email_from=self.env.user.email_formatted or company.email or self.env.ref('base.user_admin').email_formatted,
                    body=_('Email notification could not be queued: assign an active '
                           'user with an email address and access to this record to %s.', group.name),
                    subtype_xmlid='mail.mt_note')
                continue
            url = '%s/web#id=%s&model=%s&view_type=form' % (
                record.get_base_url(), record.id, record._name)
            self.env['mail.mail'].sudo().create({
                'subject': _('%(stage)s: %(record)s', stage=stage, record=record.display_name),
                'email_to': ','.join(sorted(recipients)),
                'email_from': company.email or self.env.user.email_formatted or self.env.ref('base.user_admin').email_formatted,
                'body_html': Markup('<p>%s</p><p><a href="%s">%s</a></p>') % (
                    stage, url, record.display_name),
                'model': record._name, 'res_id': record.id,
                'auto_delete': False,
            })
