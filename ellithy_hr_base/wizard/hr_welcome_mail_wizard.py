from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

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
        if employee.welcome_email_sent:
            raise ValidationError(_(
                'The onboarding mail has already been sent to %(name)s.',
                name=employee.name))
        if not self.email_to:
            raise ValidationError(_('There is no address to send to.'))

        company = employee.company_id or self.env.company
        mail = self.env['mail.mail'].sudo().create({
            'subject': self.subject,
            'body_html': self.body_html,
            'email_to': self.email_to,
            'email_cc': self.email_cc or False,
            'email_from': company.email or self.env.user.email_formatted,
            'author_id': self.env.user.partner_id.id,
            'attachment_ids': [(6, 0, self.attachment_ids.ids)],
            'auto_delete': False,
        })
        mail.send()

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
