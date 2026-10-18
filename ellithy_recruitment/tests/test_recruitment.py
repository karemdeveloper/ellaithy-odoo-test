import re
from datetime import datetime

from odoo.tests import HttpCase, TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestRecruitmentFlow(TransactionCase):
    """Recruitment items 3, 4, 6, 7, 9 and 11."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.grade = cls.env['ellithy.hr.grade'].create({'name': 'Test Grade'})
        cls.env['ellithy.interview.question'].create([
            {'grade_id': cls.grade.id, 'name': 'Q1'}, {'grade_id': cls.grade.id, 'name': 'Q2'}])
        cls.job = cls.env['hr.job'].create({'name': 'Test Seller', 'grade_id': cls.grade.id})
        cls.interviewer = cls.env['hr.employee'].create(
            {'name': 'Interviewing Manager', 'work_email': 'interviewer@example.com'})
        candidate = cls.env['hr.candidate'].create(
            {'partner_name': 'Test Candidate', 'national_id': '29001011234567'})
        cls.applicant = cls.env['hr.applicant'].create(
            {'candidate_id': candidate.id, 'job_id': cls.job.id})

    def test_stages_follow_the_agreed_list(self):
        names = self.env['hr.recruitment.stage'].search([]).mapped('name')
        for name in ('Phone Screen', 'Third Interview', 'Job Fit', 'Not Fit', 'Hired',
                     'Rejected', 'Maybe', 'Maybe for Another Job', 'Not Interested', 'Pending'):
            self.assertIn(name, names)
        rejected = self.env.ref('ellithy_recruitment.stage_rejected')
        self.assertTrue(rejected.template_id, 'moving to Rejected mails the candidate')

    def test_scheduling_the_second_interview_notifies_the_interviewer(self):
        wizard = self.env['ellithy.interview.schedule.wizard'].create({
            'applicant_id': self.applicant.id, 'interview_round': 'second',
            'interviewer_id': self.interviewer.id, 'start': datetime(2026, 10, 20, 9, 0)})
        wizard.action_schedule()
        self.assertEqual(self.applicant.stage_id.interview_round, 'second')
        self.assertIn(self.interviewer, self.applicant.interviewer_employee_ids)
        evaluation = self.applicant.evaluation_ids
        self.assertEqual(evaluation.line_ids.mapped('question'), ['Q1', 'Q2'])
        mail = self.env['mail.mail'].search([
            ('model', '=', 'hr.applicant'), ('res_id', '=', self.applicant.id),
            ('email_to', '=', 'interviewer@example.com')])
        self.assertTrue(mail)

    def test_evaluation_scores_as_a_percentage(self):
        action = self.applicant.action_new_evaluation()
        self.assertEqual(len(action['context']['default_line_ids']), 2)
        evaluation = self.env['ellithy.applicant.evaluation'].create(
            self.applicant._new_evaluation_vals('first', self.interviewer))
        evaluation.line_ids[0].rating = '5'
        evaluation.line_ids[1].rating = '3'
        evaluation.action_submit()
        self.assertEqual(evaluation.score, 80.0)
        self.assertEqual(self.applicant.evaluation_score, 80.0)

    def test_dragging_into_an_interview_round_asks_for_an_interviewer(self):
        third = self.env.ref('ellithy_recruitment.stage_third_interview')
        self.applicant.stage_id = third
        self.assertTrue(self.applicant.activity_ids.filtered(
            lambda a: 'Third Interview' in (a.summary or '')))

    def test_manpower_shortage_is_required_minus_current(self):
        department = self.env['hr.department'].create({'name': 'Shortage Dept'})
        self.env['hr.employee'].create({'name': 'In Post', 'job_id': self.job.id,
                                        'department_id': department.id})
        request = self.env['ellithy.manpower.request'].create({
            'department_id': department.id, 'job_id': self.job.id, 'required_count': 4})
        self.assertEqual(request.current_count, 1)
        self.assertEqual(request.shortage, 3)
        request.action_open()
        self.assertEqual(self.job.no_of_recruitment, 3)

    def test_contact_log_schedules_the_follow_up(self):
        candidate = self.env['hr.candidate'].create({'partner_name': 'WhatsApp Lead'})
        self.env['ellithy.candidate.contact'].create({
            'candidate_id': candidate.id, 'channel': 'whatsapp', 'result': 'call_back',
            'follow_up_date': '2026-10-25'})
        self.assertEqual(candidate.contact_count, 1)
        self.assertEqual(str(candidate.activity_ids.date_deadline), '2026-10-25')


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestCareersPage(HttpCase):
    """Recruitment items 1, 2 and 8: the public application form."""

    def test_applying_from_the_qr_link_creates_the_application(self):
        job = self.env['hr.job'].create({'name': 'Public Seller', 'online_apply': True})
        self.authenticate(None, None)  # anonymous, but on the test database
        page = self.url_open('/careers/%s?src=qr' % job.id)
        self.assertEqual(page.status_code, 200)
        token = re.search(r'name="csrf_token" value="([^"]+)"', page.text).group(1)
        response = self.url_open('/careers/%s' % job.id, data={
            'csrf_token': token, 'src': 'qr', 'name': 'QR Walk-in',
            'phone': '01000000009', 'national_id': '29501011234567',
            'military_status': 'completed', 'notice_period_days': '15',
        })
        self.assertEqual(response.status_code, 200)
        applicant = self.env['hr.applicant'].search([('job_id', '=', job.id)])
        self.assertEqual(applicant.partner_name, 'QR Walk-in')
        self.assertEqual(applicant.national_id, '29501011234567')
        self.assertEqual(applicant.source_id, self.env.ref('ellithy_recruitment.utm_source_qr_code'))
