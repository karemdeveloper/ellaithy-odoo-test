from odoo import _, api, fields, models

CHANNEL = [
    ('phone', 'Phone'),
    ('whatsapp', 'WhatsApp'),
    ('email', 'Email'),
    ('in_person', 'In Person'),
    ('other', 'Other'),
]

RESULT = [
    ('interested', 'Interested'),
    ('not_interested', 'Not Interested'),
    ('no_answer', 'No Answer'),
    ('call_back', 'Call Back Later'),
    ('interview', 'Interview Scheduled'),
    ('wrong_number', 'Wrong Number'),
    ('other', 'Other'),
]


class CandidateContact(models.Model):
    """One call, message or meeting with a candidate.

    Recruiters reach many people before any of them applies, so this is
    kept on the candidate, with or without an application.
    """

    _name = 'ellithy.candidate.contact'
    _description = 'Candidate Contact'
    _order = 'date desc, id desc'

    candidate_id = fields.Many2one(
        'hr.candidate', string='Candidate', required=True, index=True,
        ondelete='cascade')
    job_id = fields.Many2one('hr.job', string='Job Discussed')
    date = fields.Datetime(default=fields.Datetime.now, required=True)
    channel = fields.Selection(CHANNEL, string='Channel', required=True, default='phone')
    result = fields.Selection(RESULT, string='Result', required=True)
    notes = fields.Text()
    follow_up_date = fields.Date(string='Follow-up Date')
    user_id = fields.Many2one(
        'res.users', string='Contacted By', default=lambda self: self.env.user)

    @api.model_create_multi
    def create(self, vals_list):
        contacts = super().create(vals_list)
        contacts._schedule_follow_up()
        for contact in contacts:
            contact.candidate_id.message_post(body=_(
                '%(channel)s contact: %(result)s. %(notes)s',
                channel=dict(CHANNEL)[contact.channel],
                result=dict(RESULT)[contact.result],
                notes=contact.notes or ''))
        return contacts

    def _schedule_follow_up(self):
        call = self.env.ref('mail.mail_activity_data_call', raise_if_not_found=False)
        for contact in self.filtered('follow_up_date'):
            contact.candidate_id.activity_schedule(
                activity_type_id=call.id if call else False,
                date_deadline=contact.follow_up_date,
                summary=_('Follow up (%(channel)s)', channel=dict(CHANNEL)[contact.channel]),
                note=contact.notes or '',
                user_id=contact.user_id.id or self.env.user.id)
