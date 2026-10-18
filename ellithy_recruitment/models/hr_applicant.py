from odoo import _, api, fields, models

from .interview import ROUNDS


class HrApplicant(models.Model):
    _inherit = 'hr.applicant'

    # ---- person-level fields, kept on the candidate ----------------------
    national_id = fields.Char(related='candidate_id.national_id', readonly=False)
    birthdate = fields.Date(related='candidate_id.birthdate', readonly=False)
    marital_status = fields.Selection(
        related='candidate_id.marital_status', readonly=False)
    military_status = fields.Selection(
        related='candidate_id.military_status', readonly=False)
    previous_job_title = fields.Char(
        related='candidate_id.previous_job_title', readonly=False)
    previous_experience_years = fields.Float(
        related='candidate_id.previous_experience_years', readonly=False)
    previous_experience = fields.Text(
        related='candidate_id.previous_experience', readonly=False)
    language_ids = fields.Many2many(
        related='candidate_id.language_ids', readonly=False)
    notice_period_days = fields.Integer(
        related='candidate_id.notice_period_days', readonly=False)

    # ---- interviewers are employees ----------------------------------------
    # Stock interviewers are users, and only a handful of employees have a
    # login. HR picks from the employee directory; those who do have a login
    # are also added to the stock field so they can open the application.
    interviewer_employee_ids = fields.Many2many(
        'hr.employee', 'hr_applicant_interviewer_employee_rel',
        'applicant_id', 'employee_id', string='Interviewing Employees',
        help='Employees who interview this applicant.')

    evaluation_ids = fields.One2many(
        'ellithy.applicant.evaluation', 'applicant_id', string='Interview Evaluations')
    evaluation_count = fields.Integer(compute='_compute_evaluation_stats')
    evaluation_score = fields.Float(
        string='Interview Score (%)', compute='_compute_evaluation_stats',
        digits=(5, 1), help='Average of the submitted interview evaluations.')

    @api.depends('evaluation_ids.score', 'evaluation_ids.state')
    def _compute_evaluation_stats(self):
        for applicant in self:
            done = applicant.evaluation_ids.filtered(lambda e: e.state == 'done')
            applicant.evaluation_count = len(applicant.evaluation_ids)
            applicant.evaluation_score = (
                sum(done.mapped('score')) / len(done) if done else 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        applicants = super().create(vals_list)
        applicants._sync_interviewer_users()
        return applicants

    def write(self, vals):
        old_stages = {applicant.id: applicant.stage_id for applicant in self}
        result = super().write(vals)
        if 'interviewer_employee_ids' in vals:
            self._sync_interviewer_users()
        if 'stage_id' in vals:
            self.filtered(
                lambda a: a.stage_id != old_stages.get(a.id)
            )._ask_for_interviewer()
        return result

    def _sync_interviewer_users(self):
        for applicant in self:
            users = applicant.interviewer_employee_ids.user_id - applicant.interviewer_ids
            if users:
                applicant.sudo().interviewer_ids = [(4, user.id) for user in users]

    def _ask_for_interviewer(self):
        """A round reached without anyone scheduled gets a to-do for the
        recruiter, so a drag on the kanban cannot skip the interviewer."""
        todo = self.env.ref('mail.mail_activity_data_todo', raise_if_not_found=False)
        rounds = dict(ROUNDS)
        for applicant in self:
            interview_round = applicant.stage_id.interview_round
            if not interview_round:
                continue
            if applicant.evaluation_ids.filtered(
                    lambda e: e.interview_round == interview_round):
                continue
            applicant.activity_schedule(
                activity_type_id=todo.id if todo else False,
                summary=_('Schedule the %(round)s', round=rounds[interview_round]),
                note=_('Choose the interviewer and time with "Schedule Interview".'),
                user_id=(applicant.user_id or self.env.user).id)

    def action_schedule_interview(self):
        self.ensure_one()
        interview_round = self.stage_id.interview_round or 'first'
        return {
            'type': 'ir.actions.act_window',
            'name': _('Schedule Interview'),
            'res_model': 'ellithy.interview.schedule.wizard',
            'view_mode': 'form', 'target': 'new',
            'context': {
                'default_applicant_id': self.id,
                'default_interview_round': interview_round,
            },
        }

    def _new_evaluation_vals(self, interview_round, interviewer):
        self.ensure_one()
        return {
            'applicant_id': self.id,
            'interview_round': interview_round,
            'interviewer_id': interviewer.id,
            'line_ids': [(0, 0, {'question': q.name, 'sequence': q.sequence})
                         for q in self.job_id._interview_questions()],
        }

    def action_new_evaluation(self):
        """Open a new evaluation, pre-filled with the job grade's questions.

        Not saved until the interviewer saves it, so opening the form by
        mistake leaves nothing behind.
        """
        self.ensure_one()
        interviewer = self.env.user.employee_id or self.interviewer_employee_ids[:1]
        vals = self._new_evaluation_vals(
            self.stage_id.interview_round or 'first', interviewer)
        context = {'default_%s' % key: value for key, value in vals.items()}
        return {
            'type': 'ir.actions.act_window', 'name': _('Interview Evaluation'),
            'res_model': 'ellithy.applicant.evaluation',
            'view_mode': 'form', 'target': 'current', 'context': context,
        }

    def action_view_evaluations(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Interview Evaluations'),
            'res_model': 'ellithy.applicant.evaluation', 'view_mode': 'list,form',
            'domain': [('applicant_id', '=', self.id)],
            'context': {'default_applicant_id': self.id},
        }
