from datetime import date, timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestTrainingEvaluation(TransactionCase):
    """HR letter items 7 and 8: training history and the trainee's rating."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        branch = cls.env['ellithy.branch'].create(
            {'name': 'Evaluation Branch', 'company_id': cls.env.company.id})
        cls.trainer = cls.env['training.trainer'].create({'name': 'Coach Omar'})
        cls.trainees = cls.env['hr.employee'].create([
            {'name': 'Rated A', 'branch_id': branch.id, 'work_email': 'rated.a@example.com'},
            {'name': 'Rated B', 'branch_id': branch.id, 'work_email': 'rated.b@example.com'},
            {'name': 'No Email', 'branch_id': branch.id},
        ])
        cls.training = cls.env['training.training'].create({
            'employee_ids': [(6, 0, cls.trainees.ids)],
            'training_type_id': cls.env['training.type'].create(
                {'name': 'Customer Care', 'code': 'UAT-CARE'}).id,
            'trainer_id': cls.trainer.id,
            'date_start': date(2026, 10, 11), 'date_end': date(2026, 10, 15),
            'category': 'internal',
        })
        cls.survey = cls.env.ref('hr_training_management.survey_training_evaluation')

    def _participant(self, employee):
        return self.training.participant_ids.filtered(
            lambda p: p.employee_id == employee)

    def _answer(self, participant, training_points, trainer_points):
        answer = participant.evaluation_input_id
        for question in self.survey.question_ids.filtered('training_eval_part'):
            points = (training_points if question.training_eval_part == 'training'
                      else trainer_points)
            choice = question.suggested_answer_ids.filtered(
                lambda a: a.answer_score == points)
            answer._save_lines(question, choice.id)
        answer._mark_done()

    def test_the_training_uses_the_evaluation_form_by_default(self):
        self.assertEqual(self.training.evaluation_survey_id, self.survey)
        self.assertTrue(self.survey.is_hr_evaluation)

    def test_sending_mails_a_link_to_every_trainee_with_an_email(self):
        self.training.action_send_evaluation()
        a, b, no_email = (self._participant(e) for e in self.trainees)
        self.assertEqual(a.evaluation_state, 'sent')
        self.assertIn('/survey/start/', a.evaluation_url)
        self.assertFalse(no_email.evaluation_state)
        mails = self.env['mail.mail'].search([
            ('model', '=', 'training.participant'), ('res_id', 'in', (a | b).ids)])
        self.assertEqual(len(mails), 2)
        self.assertIn(a.evaluation_input_id.access_token, mails.filtered(
            lambda m: m.res_id == a.id).body_html)
        self.assertTrue(self.training.evaluation_sent_at)

    def test_ratings_are_split_between_training_and_trainer(self):
        self.training.action_send_evaluation()
        a = self._participant(self.trainees[0])
        self._answer(a, training_points=5, trainer_points=3)
        self.assertEqual(a.evaluation_state, 'done')
        self.assertEqual(a.training_rating, 100.0)
        self.assertEqual(a.trainer_rating, 60.0)
        self.assertEqual(a.evaluation_score, 80.0)

    def test_the_programme_and_trainer_show_the_average(self):
        self.training.action_send_evaluation()
        a, b = (self._participant(e) for e in self.trainees[:2])
        self._answer(a, 5, 5)
        self._answer(b, 3, 4)
        self.assertEqual(self.training.evaluation_progress, '2 / 3')
        self.assertEqual(self.training.training_rating, 80.0)
        self.assertEqual(self.training.trainer_rating, 90.0)
        self.trainer.invalidate_recordset()
        self.assertEqual(self.trainer.trainer_rating, 90.0)
        self.assertEqual(self.trainer.evaluation_count, 2)

    def test_the_daily_job_sends_once_after_the_end_date(self):
        Training = self.env['training.training']
        with patch.object(fields.Date, 'context_today',
                          return_value=date(2026, 10, 15)):
            Training._cron_send_evaluations()
        self.assertFalse(self.training.evaluation_sent_at, 'not on the last day itself')
        with patch.object(fields.Date, 'context_today',
                          return_value=date(2026, 10, 16)):
            Training._cron_send_evaluations()
            sent_at = self.training.evaluation_sent_at
            self.assertTrue(sent_at)
            Training._cron_send_evaluations()
        self.assertEqual(self.training.evaluation_sent_at, sent_at)

    def test_an_old_programme_is_not_mailed_by_the_job(self):
        with patch.object(fields.Date, 'context_today',
                          return_value=date(2026, 10, 15) + timedelta(days=60)):
            self.env['training.training']._cron_send_evaluations()
        self.assertFalse(self.training.evaluation_sent_at)

    def test_the_employee_file_lists_the_training(self):
        employee = self.trainees[0]
        self.assertIn(self.training, employee.training_participant_ids.training_id)
        arch = self.env['hr.employee'].get_view(
            self.env.ref('hr.view_employee_form').id)['arch']
        self.assertIn('name="training_history"', arch)
