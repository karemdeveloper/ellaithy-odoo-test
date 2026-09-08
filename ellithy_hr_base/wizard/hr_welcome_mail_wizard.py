from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

TEMPLATE = 'ellithy_hr_base.mail_template_employee_welcome'


class EllithyHrWelcomeMailWizard(models.TransientModel):
    """Review the onboarding mail, then send it.

    The template is rendered into the wizard rather than sent straight from
    the button, so the body arrives filled in with this employee's details
    and HR can still change it. A welcome is the first thing the company says
    to someone; it is worth reading before it goes.

    Editing here changes this message only. The template itself is left
    alone, so the next joiner still gets the standard wording.
    """

    _name = 'ellithy.hr.welcome.mail.wizard'
    _description = 'Send Onboarding Mail'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')
    mail_id = fields.Many2one('mail.mail', readonly=True, copy=False)
    company_id = fields.Many2one(
        related='employee_id.company_id', string='Company')

    email_to = fields.Char(
        string='To', required=True,
        compute='_compute_from_template', store=True, readonly=False,
        precompute=True)
    email_cc = fields.Char(
        string='Cc', help='Copy the line manager or the onboarding buddy.')
    subject = fields.Char(
        string='Subject', required=True,
        compute='_compute_from_template', store=True, readonly=False,
        precompute=True)
    body_html = fields.Html(
        string='Message', sanitize=False,
        compute='_compute_from_template', store=True, readonly=False,
        precompute=True)

    attachment_ids = fields.Many2many(
        'ir.attachment', string='Attachments',
        help='Handbook, policies, anything the joiner should have on day one.')

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and (self.env.context.get('default_mail_id')
                               or any(v.get('mail_id') for v in vals_list)):
            raise AccessError(_('The welcome mail reference is assigned by Send.'))
        return super().create(vals_list)

    def write(self, vals):
        if 'mail_id' in vals and not self.env.su:
            raise AccessError(_('The welcome mail reference is assigned by Send.'))
        if vals.get('employee_id') and any(
                w.mail_id and w.employee_id.id != vals['employee_id'] for w in self):
            raise ValidationError(_('Open a new welcome review for another employee.'))
        return super().write(vals)

    @api.depends('employee_id')
    def _compute_from_template(self):
        """Fill the wizard with the rendered template."""
        template = self.env.ref(TEMPLATE, raise_if_not_found=False)
        for wizard in self:
            employee = wizard.employee_id
            if not template or not employee:
                wizard.email_to = employee.work_email or ''
                wizard.subject = ''
                wizard.body_html = ''
                continue
            rendered = template._render_field(
                'body_html', employee.ids, compute_lang=True)[employee.id]
            subject = template._render_field(
                'subject', employee.ids, compute_lang=True)[employee.id]
            wizard.email_to = employee.work_email or ''
            wizard.subject = subject
            wizard.body_html = rendered

    def action_send(self):
        self.ensure_one()
        employee = self.employee_id
        employee.check_access('write')
        # Serialize two open review windows for the same employee.
        self.env.cr.execute('UPDATE hr_employee SET id = id WHERE id = %s', [employee.id])
        employee.invalidate_recordset(['welcome_email_sent'])
        if employee.welcome_email_sent:
            raise ValidationError(_(
                'The onboarding mail has already been sent to %(name)s.',
                name=employee.name))
        if not self.email_to:
            raise ValidationError(_('There is no address to send to.'))

        company = employee.company_id or self.env.company
        values = {
            'subject': self.subject,
            'body_html': self.body_html,
            'email_to': self.email_to,
            'email_cc': self.email_cc or False,
            'email_from': company.email or self.env.user.email_formatted,
            'author_id': self.env.user.partner_id.id,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'auto_delete': False,
        }
        mail = self.mail_id.sudo()
        if mail and mail.state != 'sent':
            mail.write(dict(values, state='outgoing', failure_reason=False))
        elif not mail:
            mail = self.env['mail.mail'].sudo().create(values)
            self.sudo().mail_id = mail
        mail.send()
        if mail.state != 'sent':
            return {
                'type': 'ir.actions.client', 'tag': 'display_notification',
                'params': {'title': _('Welcome email was not sent'),
                           'message': _('Check the outgoing mail server and try Send again. '
                                        'The employee has not been marked as welcomed.'),
                           'type': 'warning', 'sticky': True},
            }

        employee.write({
            'welcome_email_sent': True,
            'welcome_email_sent_on': fields.Datetime.now(),
            'welcome_email_sent_by': self.env.user.id,
        })
        # Logged on the employee, so the audit trail carries it too.
        employee.message_post(
            body=_('Onboarding mail sent to %(address)s.',
                   address=self.email_to),
            attachment_ids=self.attachment_ids.ids)
        return {'type': 'ir.actions.act_window_close'}
