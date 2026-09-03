from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

STATUS = [
    ('draft', 'Draft'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
]


class IbsHrWarning(models.Model):
    """A disciplinary penalty issued to an employee.

    Legacy `employee_warnings`, 2,502 rows. The occurrence number selects a
    rung of the violation's ladder, which yields the day count that reaches
    payroll as a deduction.
    """

    _name = 'ibs.hr.warning'
    _description = 'Employee Warning'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    violation_id = fields.Many2one(
        'ibs.hr.violation', string='Violation', required=True,
        ondelete='restrict', tracking=True)
    giver_id = fields.Many2one(
        'hr.employee', string='Issued By', ondelete='restrict')
    date = fields.Date(
        string='Date', required=True, default=fields.Date.context_today,
        tracking=True)

    occurrence = fields.Integer(
        string='Occurrence', compute='_compute_occurrence', store=True,
        readonly=False, tracking=True,
        help='Which time this employee has committed this violation inside '
             'the reset window. Computed, but may be overridden.')
    penalty_id = fields.Many2one(
        'ibs.hr.violation.penalty', string='Ladder Step',
        compute='_compute_penalty', store=True, readonly=False)
    action = fields.Selection(
        related='penalty_id.action', string='Action', store=True)

    penalty_days = fields.Float(
        string='Penalty (days)', digits=(6, 2), compute='_compute_penalty_days',
        store=True, readonly=False,
        help='Defaults from the ladder. Override with a reason if needed.')
    custom_penalty_days = fields.Float(
        string='Override (days)', digits=(6, 2),
        help='Legacy custom_penalty_value. Set to depart from the ladder.')
    deducted_amount = fields.Monetary(
        string='Deducted Amount', compute='_compute_deducted_amount',
        store=True, currency_field='currency_id',
        help='penalty days x daily rate, where daily rate is basic salary / 30.')
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)

    status = fields.Selection(
        STATUS, string='Status', default='draft', required=True, tracking=True)
    reviewed_by = fields.Many2one('res.users', string='Reviewed By', readonly=True)
    reviewed_at = fields.Datetime(string='Reviewed At', readonly=True)
    review_comment = fields.Text(string='Review Comment')
    notes = fields.Text()

    parent_warning_id = fields.Many2one(
        'ibs.hr.warning', string='Escalates From', ondelete='set null',
        help='Legacy parent_warning_id -- links a repeat offence to the '
             'previous one in the chain.')
    payslip_id = fields.Many2one(
        'ibs.hr.payslip', string='Deducted On', readonly=True, copy=False,
        ondelete='set null')

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another warning already carries this legacy ID.'),
    ]

    # ------------------------------------------------------------------
    @api.model
    def _reset_window_months(self):
        """Months over which repeat offences accumulate.

        NOT ESTABLISHED. The legacy database carries no reset rule and the UI
        does not expose one, so this is a placeholder that must be confirmed
        with HR before go-live. Twelve months is the common reading of the
        Egyptian Labour Law, but it is an assumption, not a migrated fact.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            'ibs_hr.violation_reset_months', '12')
        try:
            return int(param)
        except (TypeError, ValueError):
            return 12

    @api.depends('employee_id', 'violation_id', 'date')
    def _compute_occurrence(self):
        for record in self:
            if not (record.employee_id and record.violation_id and record.date):
                record.occurrence = 1
                continue
            months = record._reset_window_months()
            window_start = fields.Date.subtract(record.date, months=months)
            prior = self.search_count([
                ('employee_id', '=', record.employee_id.id),
                ('violation_id', '=', record.violation_id.id),
                ('date', '>=', window_start),
                ('date', '<', record.date),
                ('status', '=', 'approved'),
                ('id', '!=', record.id or 0),
            ])
            record.occurrence = prior + 1

    @api.depends('violation_id', 'occurrence')
    def _compute_penalty(self):
        for record in self:
            if record.violation_id and record.occurrence:
                record.penalty_id = record.violation_id.penalty_for_occurrence(
                    record.occurrence)
            else:
                record.penalty_id = False

    @api.depends('penalty_id', 'custom_penalty_days')
    def _compute_penalty_days(self):
        for record in self:
            if record.custom_penalty_days:
                record.penalty_days = record.custom_penalty_days
            else:
                record.penalty_days = record.penalty_id.penalty_days or 0.0

    @api.depends('penalty_days', 'employee_id', 'date')
    def _compute_deducted_amount(self):
        for record in self:
            record.deducted_amount = record.penalty_days * record._daily_rate()

    def _daily_rate(self):
        """Daily rate = basic salary / 30.

        Verified against 3,174 legacy payslip rows: dividing the stored
        penalty amount by basic/30 yields clean integer day counts.
        """
        self.ensure_one()
        contract = self.employee_id._ibs_contract_on(self.date)
        if not contract or not contract.wage:
            return 0.0
        return contract.wage / 30.0

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.warning') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.filtered(lambda r: r.status == 'draft').write({'status': 'pending'})

    def action_approve(self):
        for record in self:
            if record.status != 'pending':
                raise ValidationError(_(
                    'Only a pending warning can be approved.'))
            record.write({
                'status': 'approved',
                'reviewed_by': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            })

    def action_reject(self):
        for record in self:
            if not record.review_comment:
                raise ValidationError(_(
                    'Rejecting a warning requires a review comment.'))
            record.write({
                'status': 'rejected',
                'reviewed_by': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            })

    def action_reset_draft(self):
        self.write({'status': 'draft', 'reviewed_by': False,
                    'reviewed_at': False})
