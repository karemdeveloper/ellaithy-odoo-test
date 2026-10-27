from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# The legacy `violation_penalties`.`action` column is free text and holds 19
# distinct spellings of roughly eight real actions, several with embedded
# newlines and typos. Migration must map onto this canonical set rather than
# carrying the raw strings across.
PENALTY_ACTION = [
    ('warning', 'Warning'),                       # إنذار
    ('fine', 'Fine'),                             # جزاء  - value in days
    ('deduction', 'Deduction'),                   # خصم   - value in days
    ('dismissal_warning', 'Warning of Dismissal'), # إنذار بالفصل
    ('allowance_cut', 'Annual Allowance Reduction'),
    ('allowance_half', 'Half Allowance Withheld'),
    ('allowance_defer', 'Allowance Deferred'),
    ('promotion_defer', 'Promotion Deferred'),
    ('demotion', 'Demotion'),
    ('dismissal', 'Dismissal'),
    ('dismissal_court', 'Dismissal via Labour Court'),
]

# Actions whose penalty_value is a day count that reaches payroll.
MONETARY_ACTIONS = ('fine', 'deduction')


class IbsHrViolation(models.Model):
    """Catalogue of disciplinary violations.

    Migrated verbatim from the legacy `violations` table (72 rows of Egyptian
    labour law text). The escalation ladder lives in the penalty lines.
    """

    _name = 'ibs.hr.violation'
    _description = 'Disciplinary Violation'
    _order = 'code, id'

    name = fields.Char(string='Violation', required=True, translate=True)
    code = fields.Char(string='Code', index=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    penalty_ids = fields.One2many(
        'ibs.hr.violation.penalty', 'violation_id', string='Escalation Ladder')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another violation already carries this legacy ID.'),
    ]

    @api.constrains('penalty_ids')
    def _check_ladder(self):
        for record in self:
            occurrences = record.penalty_ids.mapped('occurrence')
            if len(occurrences) != len(set(occurrences)):
                raise ValidationError(_(
                    'Violation "%(name)s" has two penalties for the same '
                    'occurrence.', name=record.name))

    def penalty_for_occurrence(self, occurrence):
        """Return the ladder rung that applies at this occurrence number.

        Occurrences beyond the top of the ladder stay on the last rung rather
        than falling through to nothing -- a fifth offence is at least as
        serious as the fourth.
        """
        self.ensure_one()
        ladder = self.penalty_ids.sorted('occurrence')
        if not ladder:
            return self.env['ibs.hr.violation.penalty']
        exact = ladder.filtered(lambda p: p.occurrence == occurrence)
        return exact[:1] if exact else ladder[-1]


class IbsHrViolationPenalty(models.Model):
    """One rung of a violation's escalation ladder."""

    _name = 'ibs.hr.violation.penalty'
    _description = 'Violation Penalty Step'
    _order = 'violation_id, occurrence'

    violation_id = fields.Many2one(
        'ibs.hr.violation', string='Violation', required=True,
        ondelete='cascade', index=True)
    occurrence = fields.Integer(
        string='Occurrence', required=True, default=1,
        help='1st, 2nd, 3rd or 4th time the employee commits this violation.')
    action = fields.Selection(
        PENALTY_ACTION, string='Action', required=True, default='fine')
    penalty_days = fields.Float(
        string='Penalty (days)', digits=(6, 2),
        help='Number of days of pay withheld. Only meaningful for fine and '
             'deduction; other actions are non-monetary and carry zero.')
    notes = fields.Text()
    legacy_action = fields.Char(
        string='Legacy Action Text', copy=False,
        help='Raw free-text value from the legacy table, kept for audit.')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    @api.constrains('occurrence')
    def _check_occurrence(self):
        for record in self:
            if record.occurrence < 1:
                raise ValidationError(_('Occurrence must be 1 or greater.'))

    @api.constrains('action', 'penalty_days')
    def _check_penalty_days(self):
        for record in self:
            if record.penalty_days < 0:
                raise ValidationError(_('Penalty days cannot be negative.'))
            if record.action not in MONETARY_ACTIONS and record.penalty_days:
                raise ValidationError(_(
                    'Action "%(action)s" is non-monetary and cannot carry a '
                    'day value.',
                    action=dict(PENALTY_ACTION).get(record.action)))

    @property
    def is_monetary(self):
        self.ensure_one()
        return self.action in MONETARY_ACTIONS
