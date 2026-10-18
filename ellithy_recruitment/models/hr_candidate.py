import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MARITAL = [
    ('single', 'Single'),
    ('married', 'Married'),
    ('divorced', 'Divorced'),
    ('widower', 'Widowed'),
]

MILITARY = [
    ('completed', 'Completed'),
    ('exempted', 'Exempted'),
    ('postponed', 'Postponed'),
    ('in_service', 'Currently Serving'),
    ('not_applicable', 'Not Applicable'),
]

# The person-level facts HR asked to record on every application. They live
# on the candidate, so a second application by the same person reuses them.
CANDIDATE_FIELDS = (
    'national_id', 'birthdate', 'marital_status', 'military_status',
    'previous_job_title', 'previous_experience_years', 'previous_experience',
    'language_ids', 'notice_period_days',
)


class HrCandidate(models.Model):
    _inherit = 'hr.candidate'

    national_id = fields.Char(string='National ID', size=14, tracking=True)
    birthdate = fields.Date(string='Birthdate')
    marital_status = fields.Selection(MARITAL, string='Marital Status')
    military_status = fields.Selection(MILITARY, string='Military Status')
    previous_job_title = fields.Char(string='Previous Job Title')
    previous_experience_years = fields.Float(
        string='Years of Experience', digits=(4, 1))
    previous_experience = fields.Text(string='Previous Experience')
    language_ids = fields.Many2many(
        'ellithy.recruitment.language', string='Languages')
    notice_period_days = fields.Integer(
        string='Notice Period (days)',
        help='How long the candidate needs before starting.')
    contact_ids = fields.One2many(
        'ellithy.candidate.contact', 'candidate_id', string='Contact Log')
    contact_count = fields.Integer(compute='_compute_contact_count')

    _sql_constraints = [
        ('national_id_uniq', 'unique(national_id, company_id)',
         'A candidate with this national ID already exists.'),
    ]

    @api.constrains('national_id')
    def _check_national_id(self):
        for candidate in self:
            if candidate.national_id and not re.fullmatch(r'\d{14}', candidate.national_id):
                raise ValidationError(_('The national ID must be 14 digits.'))

    def _compute_contact_count(self):
        data = self.env['ellithy.candidate.contact']._read_group(
            [('candidate_id', 'in', self.ids)], ['candidate_id'], ['__count'])
        counts = {candidate.id: count for candidate, count in data}
        for candidate in self:
            candidate.contact_count = counts.get(candidate.id, 0)

    def action_view_contacts(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Contact Log'),
            'res_model': 'ellithy.candidate.contact', 'view_mode': 'list,form',
            'domain': [('candidate_id', '=', self.id)],
            'context': {'default_candidate_id': self.id},
        }

    def _get_employee_create_vals(self):
        """Carry what the candidate told us onto the new employee file."""
        vals = super()._get_employee_create_vals()
        vals.update({
            'identification_id': self.national_id or False,
            'birthday': self.birthdate or False,
        })
        if self.marital_status:
            vals['marital'] = self.marital_status
        return vals
