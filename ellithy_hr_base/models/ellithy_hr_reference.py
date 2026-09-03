from odoo import fields, models


class EllithyHrSuspensionReason(models.Model):
    """Suspension reason picklist.

    The legacy keeps both a dropdown (``suspension_reason_dropdown``) and a
    free-text comment (``suspension_reason``). Only the dropdown is modelled
    here; the comment stays a plain text field on the employee.
    """

    _name = 'ellithy.hr.suspension.reason'
    _description = 'Suspension Reason'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    legacy_value = fields.Char(string='Legacy Value', index=True)


class EllithyHrInsuranceOffice(models.Model):
    """Social insurance office."""

    _name = 'ellithy.hr.insurance.office'
    _description = 'Social Insurance Office'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    name_ar = fields.Char(string='Arabic Name')
    code = fields.Char(string='Code', index=True)
    active = fields.Boolean(default=True)
    employee_ids = fields.One2many(
        'hr.employee', 'social_insurance_office_id', string='Employees')
    employee_count = fields.Integer(
        string='Employee Count', compute='_compute_employee_count')
    legacy_value = fields.Char(
        string='Legacy Value', index=True,
        help='One of the raw spellings found in the source. The source holds '
             'nine variants of these four offices; migration normalises them.')

    def _compute_employee_count(self):
        data = self.env['hr.employee']._read_group(
            [('social_insurance_office_id', 'in', self.ids)],
            ['social_insurance_office_id'], ['__count'])
        mapped = {office.id: count for office, count in data}
        for record in self:
            record.employee_count = mapped.get(record.id, 0)


class EllithyHrDocumentType(models.Model):
    """HR file document type.

    The legacy stores fourteen fixed upload columns on ``users``. Modelling
    them as a type reference plus per-employee lines makes file completeness
    reportable instead of implied by fourteen nullable columns.
    """

    _name = 'ellithy.hr.document.type'
    _description = 'HR Document Type'
    _order = 'sequence, name'

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    required = fields.Boolean(
        string='Required',
        help='Counts towards the employee file completeness percentage.')
    legacy_column = fields.Char(
        string='Legacy Column', index=True,
        help='Column on the legacy users table this type was migrated from.')


class EllithyHrUniform(models.Model):
    """A uniform item that can be issued to employees.

    The legacy keeps these in `uniforms` with a many-to-many `uniform_user`
    join, so an employee can hold several items at once. Separate from the
    ``has_uniform`` entitlement flag, which only records whether they are
    entitled to one at all.
    """

    _name = 'ellithy.hr.uniform'
    _description = 'Uniform Item'
    _order = 'name'

    name = fields.Char(required=True, translate=True)
    distributor = fields.Char(string='Distributor')
    price = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(
        'res.currency', default=lambda self: self.env.company.currency_id)
    stock = fields.Integer(string='Stock')
    active = fields.Boolean(default=True)
    employee_ids = fields.Many2many(
        'hr.employee', 'ellithy_hr_uniform_employee_rel',
        'uniform_id', 'employee_id', string='Issued To')
    employee_count = fields.Integer(
        string='Issued Count', compute='_compute_employee_count')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another uniform already carries this legacy ID.'),
    ]

    def _compute_employee_count(self):
        for record in self:
            record.employee_count = len(record.employee_ids)
