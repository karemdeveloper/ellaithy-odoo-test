from datetime import date

from odoo.exceptions import UserError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install', 'ellithy_hr')
class TestSessionsAndAssessments(TransactionCase):
    """HR letter items 9 and 10."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        branch = cls.env['ellithy.branch'].create(
            {'name': 'Training Branch', 'company_id': cls.env.company.id})
        cls.trainees = cls.env['hr.employee'].create([
            {'name': 'Trainee A', 'branch_id': branch.id, 'work_email': 'a@example.com'},
            {'name': 'Trainee B', 'branch_id': branch.id},
        ])
        cls.training = cls.env['training.training'].create({
            'employee_ids': [(6, 0, cls.trainees.ids)],
            'training_type_id': cls.env['training.type'].create({'name': 'Sales', 'code': 'UAT-SALES'}).id,
            'date_start': date(2026, 10, 11), 'date_end': date(2026, 10, 15),
            'category': 'internal',
        })

    def test_sessions_track_attendance_per_trainee(self):
        self.training.action_generate_sessions()
        sessions = self.training.session_ids
        self.assertEqual(len(sessions), 5)
        self.assertEqual(len(sessions[0].attendance_ids), 2)
        sessions[0].attendance_ids.filtered(
            lambda a: a.employee_id == self.trainees[0]).status = 'absent'
        participant = self.training.participant_ids.filtered(
            lambda p: p.employee_id == self.trainees[0])
        self.assertEqual(participant.attended_count, 4)
        self.assertEqual(participant.attendance_rate, 80.0)

    def test_a_new_trainee_joins_existing_sessions(self):
        self.training.action_generate_sessions()
        newcomer = self.env['hr.employee'].create({'name': 'Late Trainee'})
        self.training.employee_ids = [(4, newcomer.id)]
        self.assertTrue(all(newcomer in s.attendance_ids.employee_id
                            for s in self.training.session_ids))

    def _assessment(self, marks=(30, 30, 40)):
        return self.env['training.assessment'].create({
            'name': 'Final Test', 'training_id': self.training.id,
            'question_ids': [
                (0, 0, {'question_type': 'mcq', 'name': 'Q1', 'marks': marks[0],
                        'option_ids': [(0, 0, {'name': 'Right', 'is_correct': True}),
                                       (0, 0, {'name': 'Wrong'})]}),
                (0, 0, {'question_type': 'mcq', 'name': 'Q2', 'marks': marks[1],
                        'option_ids': [(0, 0, {'name': 'Wrong'}),
                                       (0, 0, {'name': 'Right', 'is_correct': True})]}),
                (0, 0, {'question_type': 'essay', 'name': 'Q3', 'marks': marks[2]}),
            ]})

    def test_questions_must_total_one_hundred(self):
        with self.assertRaises(UserError):
            self._assessment(marks=(30, 30, 30)).action_publish()

    def test_mcq_is_marked_automatically_and_essay_by_hand(self):
        assessment = self._assessment()
        assessment.action_publish()
        assessment.action_send_to_trainees()
        attempt = assessment.attempt_ids.filtered(lambda a: a.employee_id == self.trainees[0])
        for answer in attempt.answer_ids:
            if answer.question_type == 'mcq':
                answer.option_id = answer.question_id.option_ids.filtered('is_correct')
            else:
                answer.essay_answer = 'Because.'
        attempt.action_submit()
        self.assertEqual(attempt.state, 'submitted')
        self.assertEqual(attempt.auto_score, 60.0)
        attempt.answer_ids.filtered(lambda a: a.question_type == 'essay').marks_awarded = 15
        attempt.action_finish_marking()
        self.assertEqual(attempt.score, 75.0)
        self.assertEqual(attempt.result, 'pass')
        participant = self.training.participant_ids.filtered(
            lambda p: p.employee_id == self.trainees[0])
        self.assertEqual(participant.assessment_result, 'pass')

    def test_below_seventy_fails(self):
        assessment = self._assessment()
        assessment.action_publish()
        assessment.action_send_to_trainees()
        attempt = assessment.attempt_ids[:1]
        attempt.answer_ids.filtered(lambda a: a.question_type == 'essay').essay_answer = 'x'
        attempt.action_submit()
        attempt.answer_ids.filtered(lambda a: a.question_type == 'essay').marks_awarded = 40
        attempt.action_finish_marking()
        self.assertEqual(attempt.score, 40.0)
        self.assertEqual(attempt.result, 'fail')
