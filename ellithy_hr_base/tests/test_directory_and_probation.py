from datetime import timedelta

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestDirectoryAndProbation(TransactionCase):
    """HR letter items 1, 2, 6 and 26."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.branch = cls.env['ellithy.branch'].create(
            {'name': 'Directory Branch', 'company_id': cls.env.company.id})
        cls.manager = cls.env['hr.employee'].create({
            'name': 'Probation Manager', 'branch_id': cls.branch.id,
            'work_email': 'probation.manager@example.com'})

    def _employee(self, **values):
        values.setdefault('branch_id', self.branch.id)
        return self.env['hr.employee'].create(values)

    def test_code_sorts_by_number_not_text(self):
        codes = ['ZZ-10', 'ZZ-2', '7777715']
        employees = self.env['hr.employee']
        for code in codes:
            employees |= self._employee(name=code, employee_code=code)
        ordered = self.env['hr.employee'].search(
            [('id', 'in', employees.ids)], order='employee_code').mapped('employee_code')
        self.assertEqual(ordered, ['ZZ-2', 'ZZ-10', '7777715'])

    def test_the_directory_list_is_the_default_list(self):
        arch = self.env['hr.employee'].get_views([(False, 'list')])['views']['list']['arch']
        order = ['employee_code', 'name', 'private_phone', 'department_id', 'job_id',
                 'branch_id', 'grade_id', 'work_email', 'joining_date',
                 'contract_date_start', 'contract_date_end']
        positions = [arch.index('name="%s"' % name) for name in order]
        self.assertEqual(positions, sorted(positions))

    def test_joining_sets_the_evaluation_due_date(self):
        joined = fields.Date.today() - timedelta(days=10)
        employee = self._employee(name='Joiner', joining_date=joined)
        self.assertEqual(employee.evaluation_date, joined + timedelta(days=60))

    def test_the_cron_sends_only_joiners_inside_the_window(self):
        today = fields.Date.today()
        due = self._employee(name='Due Joiner', parent_id=self.manager.id,
                             joining_date=today - timedelta(days=61))
        veteran = self._employee(name='Veteran', parent_id=self.manager.id,
                                 joining_date=today - timedelta(days=900))
        self.env['hr.employee']._cron_send_probation_evaluations()
        self.assertEqual(due.probation_state, 'pending')
        self.assertEqual(due.probation_evaluator_id, self.manager)
        self.assertEqual(veteran.probation_state, 'not_sent')
        mail = self.env['mail.mail'].search([
            ('model', '=', 'hr.employee'), ('res_id', '=', due.id)], limit=1)
        self.assertIn('probation.manager@example.com', mail.email_to)
        self.assertIn(due.probation_input_id.access_token, mail.body_html)

    def test_a_completed_survey_is_shown_on_the_employee(self):
        employee = self._employee(name='Evaluated', parent_id=self.manager.id,
                                  joining_date=fields.Date.today() - timedelta(days=61))
        employee.action_send_probation_evaluation()
        answer = employee.probation_input_id.sudo()
        survey = answer.survey_id
        for question in survey.question_ids.filtered(lambda q: q.question_type == 'simple_choice'):
            choice = question.suggested_answer_ids.sorted('sequence')[-1]
            answer._save_lines(question, choice.id)
        answer._mark_done()
        employee.invalidate_recordset()
        self.assertEqual(employee.probation_state, 'done')
        self.assertEqual(employee.probation_score, 100.0)
        self.assertIn('End employment', employee.probation_recommendation)

    def test_the_onboarding_image_appears_only_when_set(self):
        template = self.env.ref('ellithy_hr_base.mail_template_employee_welcome')
        employee = self._employee(name='Welcome Joiner', work_email='w@example.com')
        body = template._render_field('body_html', employee.ids)[employee.id]
        self.assertNotIn('onboarding_image', body)
        self.env.company.hr_onboarding_banner = (
            'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')
        body = template._render_field('body_html', employee.ids)[employee.id]
        self.assertIn('/ellithy_hr/onboarding_image/%s' % self.env.company.id, body)
