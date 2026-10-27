from odoo import fields, models


TIME_OFF_CODE_ALIASES = {
    'cas': 'casual',
    'casual': 'casual',
    'ann': 'annual',
    'annual': 'annual',
    'bd': 'birthday',
    'birthday': 'birthday',
    'ph': 'public_holiday',
    'public_holiday': 'public_holiday',
    'rest': 'compensatory_rest',
    'compensatory_rest': 'compensatory_rest',
    'other': 'other',
}


class IbsHrTimeOffType(models.Model):
    _name = 'ibs.hr.time.off.type'
    _description = 'Time Off Type'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    approval_route = fields.Selection([
        ('manager', 'HR Generalist (one step)'),
        ('hr', 'HR Generalist (one step)'),
        ('both', 'HR Generalist then HR Admin'),
    ], required=True, default='hr')
    has_attachment = fields.Boolean(string='Has Attachment')
    one_day_per_year = fields.Boolean(string='One Day per Year')
    limit_days = fields.Float(string='Limit (Days)')
    required_period_months = fields.Integer(
        string='Required Period after Joining Date')
    paid = fields.Boolean(default=True)

    code = fields.Char(required=True, default='other', index=True)
    company_id = fields.Many2one(
        'res.company', required=True, default=lambda self: self.env.company,
        ondelete='cascade')
    active = fields.Boolean(default=True)

    def _canonical_code(self):
        """Return the engine behavior while preserving the user's typed code."""
        self.ensure_one()
        normalized = (self.code or '').strip().lower().replace('-', '_').replace(' ', '_')
        return TIME_OFF_CODE_ALIASES.get(normalized, 'other')

    def _auto_init(self):
        result = super()._auto_init()
        # A company can configure several named custom types, all represented
        # by the technical `other` code. Reserved engine types remain unique.
        self.env.cr.execute(
            'ALTER TABLE ibs_hr_time_off_type '
            'DROP CONSTRAINT IF EXISTS '
            'ibs_hr_time_off_type_company_code_unique')
        self.env.cr.execute(
            'CREATE UNIQUE INDEX IF NOT EXISTS '
            'ibs_hr_time_off_type_reserved_code_unique '
            'ON ibs_hr_time_off_type (company_id, code) '
            "WHERE code <> 'other'")
        return result
