from datetime import timedelta

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.interview import ROUNDS


class InterviewScheduleWizard(models.TransientModel):
    """Pick the interviewer and time for a round, and tell them.

    Moves the application to the round's stage, books the meeting in the
    calendar, prepares the interviewer's evaluation with the job grade's
    questions, and emails the interviewer the details.
    """

    _name = 'ellithy.interview.schedule.wizard'
    _description = 'Schedule Interview'

    applicant_id = fields.Many2one('hr.applicant', required=True)
    interview_round = fields.Selection(ROUNDS, string='Round', required=True)
    interviewer_id = fields.Many2one(
        'hr.employee', string='Interviewer', required=True,
        domain="[('work_email', '!=', False)]")
    start = fields.Datetime(string='Date & Time', required=True,
                            default=lambda self: fields.Datetime.now() + timedelta(days=1))
    duration = fields.Float(string='Duration (hours)', default=1.0)
    location = fields.Char(default=lambda self: self.env.company.name)
    note = fields.Text(string='Message to the Interviewer')

    def _round_stage(self):
        return self.env['hr.recruitment.stage'].search(
            [('interview_round', '=', self.interview_round)], limit=1)

    def action_schedule(self):
        self.ensure_one()
        applicant = self.applicant_id
        employee = self.interviewer_id
        if not employee.work_email:
            raise UserError(_('%(name)s has no work email to notify.', name=employee.name))
        round_label = dict(ROUNDS)[self.interview_round]

        stage = self._round_stage()
        values = {'interviewer_employee_ids': [(4, employee.id)]}
        if stage and applicant.stage_id != stage:
            values['stage_id'] = stage.id
        # The evaluation exists before the stage moves, so the stage hook
        # sees the round as covered and adds no "schedule it" to-do.
        evaluation = self.env['ellithy.applicant.evaluation'].create(
            applicant._new_evaluation_vals(self.interview_round, employee))
        applicant.write(values)

        partner = employee.work_contact_id
        event = self.env['calendar.event'].with_context(no_mail_to_attendees=True).create({
            'name': _('%(round)s: %(name)s', round=round_label, name=applicant.partner_name),
            'start': self.start,
            'stop': self.start + timedelta(hours=self.duration or 1.0),
            'duration': self.duration or 1.0,
            'location': self.location,
            'partner_ids': [(6, 0, partner.ids)] if partner else False,
            'applicant_id': applicant.id,
            'res_model_id': self.env['ir.model']._get_id('hr.applicant'),
            'res_id': applicant.id,
        })

        url = '%s/odoo/action-ellithy_recruitment.action_applicant_evaluation/%s' % (
            applicant.get_base_url(), evaluation.id)
        body = Markup(
            '<p>%s</p><ul><li>%s: %s</li><li>%s: %s</li><li>%s: %s</li>'
            '<li>%s: %s</li></ul><p>%s</p><p><a href="%s">%s</a></p>'
        ) % (
            _('You have been chosen to conduct the %(round)s below.', round=round_label),
            _('Candidate'), applicant.partner_name,
            _('Job'), applicant.job_id.name or '-',
            _('When'), fields.Datetime.context_timestamp(self, self.start).strftime('%Y-%m-%d %H:%M'),
            _('Where'), self.location or '-',
            self.note or '',
            url, _('Open the evaluation form'))
        self.env['mail.mail'].sudo().create({
            'subject': _('%(round)s with %(name)s', round=round_label, name=applicant.partner_name),
            'email_to': employee.work_email,
            'email_from': self.env.company.email or self.env.user.email_formatted,
            'body_html': body,
            'model': 'hr.applicant', 'res_id': applicant.id,
            'auto_delete': False,
        })
        applicant.message_post(body=_(
            '%(round)s scheduled with %(who)s on %(when)s; the interviewer was emailed.',
            round=round_label, who=employee.name,
            when=fields.Datetime.context_timestamp(self, self.start).strftime('%Y-%m-%d %H:%M')))
        # Close any "schedule this round" to-do left by a kanban drag.
        applicant.activity_ids.filtered(
            lambda a: round_label in (a.summary or '')).action_done()
        return {'type': 'ir.actions.act_window_close', 'infos': {'event_id': event.id}}
