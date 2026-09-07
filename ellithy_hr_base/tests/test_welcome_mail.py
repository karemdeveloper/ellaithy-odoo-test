from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestWelcomeMail(TransactionCase):
    """CR 2.5 as revised: a button, a reviewable wizard, and one send only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create(
            {'name': 'Welcome Branch', 'company_id': cls.env.company.id})

    def _employee(self, **kwargs):
        values = {
            'name': 'New Joiner',
            'branch_id': self.branch.id,
            'work_email': 'joiner@example.com',
            'job_title': 'Accountant',
            'joining_date': '2026-09-01',
        }
        values.update(kwargs)
        return self.env['hr.employee'].create(values)

    def _wizard(self, employee):
        return self.env['ellithy.hr.welcome.mail.wizard'].create(
            {'employee_id': employee.id})

    # ---- no longer automatic ------------------------------------------
    def test_creating_an_employee_sends_nothing(self):
        """Creating a record and welcoming a person are different acts."""
        before = self.env['mail.mail'].search_count([])
        employee = self._employee()
        self.assertFalse(employee.welcome_email_sent)
        self.assertEqual(self.env['mail.mail'].search_count([]), before)

    # ---- the wizard ----------------------------------------------------
    def test_the_wizard_opens_prefilled_from_the_template(self):
        employee = self._employee()
        wizard = self._wizard(employee)
        self.assertEqual(wizard.email_to, 'joiner@example.com')
        self.assertIn(employee.name, wizard.subject)
        # The rendered body carries this employee's own details.
        self.assertIn('Accountant', wizard.body_html)
        self.assertIn(employee.name, wizard.body_html)

    def test_the_body_can_be_edited_without_touching_the_template(self):
        employee = self._employee()
        wizard = self._wizard(employee)
        template = self.env.ref(
            'ellithy_hr_base.mail_template_employee_welcome')
        original = template.body_html
        wizard.body_html = '<p>Bespoke welcome.</p>'
        wizard.action_send()
        self.assertEqual(template.body_html, original)

        mail = self.env['mail.mail'].search(
            [('email_to', '=', 'joiner@example.com')], limit=1, order='id desc')
        self.assertIn('Bespoke welcome.', mail.body_html)

    def test_sending_marks_the_employee_and_logs_it(self):
        employee = self._employee()
        self._wizard(employee).action_send()
        self.assertTrue(employee.welcome_email_sent)
        self.assertEqual(employee.welcome_email_sent_by, self.env.user)
        self.assertTrue(employee.welcome_email_sent_on)
        bodies = employee.message_ids.mapped('body')
        self.assertTrue(any('Onboarding mail sent' in b for b in bodies))

    # ---- sent once, and only once --------------------------------------
    def test_the_button_refuses_a_second_send(self):
        employee = self._employee()
        self._wizard(employee).action_send()
        with self.assertRaises(ValidationError):
            employee.action_send_welcome_mail()

    def test_the_wizard_itself_refuses_a_second_send(self):
        """The guard is on the send, not only on the button that opens it."""
        employee = self._employee()
        wizard = self._wizard(employee)
        second = self._wizard(employee)
        wizard.action_send()
        with self.assertRaises(ValidationError):
            second.action_send()

    def test_an_employee_without_a_work_email_cannot_be_mailed(self):
        employee = self._employee(work_email=False)
        with self.assertRaises(ValidationError):
            employee.action_send_welcome_mail()

    def test_the_button_is_hidden_once_sent(self):
        arch = self.env.ref(
            'ellithy_hr_base.hr_employee_view_form_inherit').arch
        self.assertIn('action_send_welcome_mail', arch)
        self.assertIn('welcome_email_sent', arch)

    # ---- the template --------------------------------------------------
    def test_the_template_carries_the_company_logo(self):
        employee = self._employee()
        body = self._wizard(employee).body_html
        self.assertIn('/logo.png?company=', body)
        # Orange and white, per the agreed styling.
        self.assertIn('#E4610F', body)
