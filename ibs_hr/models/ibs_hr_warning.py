from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

STATUS = [
    ('draft', 'Draft'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
    ('cancel', 'Cancelled'),
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
        tracking=True, help='When the violation occurred.')
    execution_date = fields.Date(
        string='Execution Date', required=True, tracking=True,
        compute='_compute_execution_date', store=True, readonly=False,
        precompute=True,
        help='CR 2.11 -- the date the deduction becomes payroll-effective. '
             'Payroll selects penalties by this date, not by the date of the '
             'violation, so a penalty raised late is still taken in the month '
             'management intends. Defaults to the date of the violation; set '
             'it forward to defer the deduction.')

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
        'hr.payslip', string='Fully Deducted On', readonly=True, copy=False,
        ondelete='set null',
        help='Set once the penalty has been taken in full. A penalty spread '
             'across months by the CR 2.12 cap stays blank until the last '
             'instalment.')

    # ---- CR 2.12: the five-day monthly ceiling and its carry-over --------
    deduction_ids = fields.One2many(
        'ibs.hr.warning.deduction', 'warning_id', string='Deductions Taken')
    days_settled = fields.Float(
        string='Days Taken', digits=(6, 2), compute='_compute_settlement',
        store=True)
    days_remaining = fields.Float(
        string='Days Outstanding', digits=(6, 2),
        compute='_compute_settlement', store=True,
        help='Days still to be deducted in a future month because the '
             'monthly ceiling was reached.')
    is_settled = fields.Boolean(
        string='Fully Deducted', compute='_compute_settlement', store=True)

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

    @api.depends('date')
    def _compute_execution_date(self):
        """Default the execution date to the date of the violation.

        Only fills a blank one: once management has deferred a penalty,
        correcting the violation date must not silently pull it back.
        """
        for record in self:
            if not record.execution_date:
                record.execution_date = record.date

    @api.depends('penalty_days', 'deduction_ids.days')
    def _compute_settlement(self):
        for record in self:
            taken = sum(record.deduction_ids.mapped('days'))
            record.days_settled = taken
            remaining = (record.penalty_days or 0.0) - taken
            record.days_remaining = max(remaining, 0.0)
            record.is_settled = (
                bool(record.penalty_days) and remaining <= 0.000001)

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
        pending = self.filtered(lambda r: r.status == 'draft')
        pending.write({'status': 'pending'})
        pending._ibs_notify_pending()

    def _ibs_approver_group(self):
        """The group whose members sign a penalty off."""
        return self.env.ref(
            'ibs_hr.group_ibs_admin_penalty_approver',
            raise_if_not_found=False)

    def _ibs_approver_emails(self):
        """Comma-separated approver addresses, for the pending-approval mail.

        Called from the mail template, so it must always return a string --
        an empty one simply means nothing is sent.
        """
        group = self._ibs_approver_group()
        if not group:
            return ''
        return ','.join(
            email for email in group.sudo().users.mapped('email') if email)

    def _ibs_notify_pending(self):
        """Tell the approvers there is something waiting."""
        template = self.env.ref(
            'ibs_hr.mail_template_penalty_pending', raise_if_not_found=False)
        if not template:
            return
        for record in self:
            template.send_mail(record.id, force_send=False)

    def _check_approver(self):
        """CR 2.13 -- only the named group decides a disciplinary penalty.

        Mirrors ``ibs.hr.admin.penalty.record._check_approver``: enforced on
        the record, not only hidden in the UI, since the list view's mass
        actions and the ORM both reach these methods directly.
        """
        if self.env.su:
            return
        if not self.env.user.has_group(
                'ibs_hr.group_ibs_admin_penalty_approver'):
            raise ValidationError(_(
                'Disciplinary penalties are decided by the Administrative '
                'Penalty Approver group. Ask an approver to action this '
                'record.'))

    def action_approve(self):
        """CR 2.14 -- one approval settles a penalty. No second signature."""
        self._check_approver()
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
        """CR 2.14 -- rejecting requires a reason."""
        self._check_approver()
        for record in self:
            if not record.review_comment:
                raise ValidationError(_(
                    'Rejecting a warning requires a review comment.'))
            record.write({
                'status': 'rejected',
                'reviewed_by': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            })

    def action_cancel(self):
        """CR 2.14 -- cancelling requires a reason, like rejecting."""
        self._check_approver()
        for record in self:
            if record.deduction_ids:
                raise ValidationError(_(
                    'This penalty has already been deducted on a payslip and '
                    'cannot be cancelled. Reset the payslip first.'))
            if not record.review_comment:
                raise ValidationError(_(
                    'Cancelling a penalty requires a reason in the review '
                    'comment.'))
            record.write({
                'status': 'cancel',
                'reviewed_by': self.env.user.id,
                'reviewed_at': fields.Datetime.now(),
            })

    def action_reset_draft(self):
        self._check_approver()
        for record in self:
            if record.deduction_ids:
                raise ValidationError(_(
                    'This penalty has already been deducted on a payslip and '
                    'cannot be reset. Reset the payslip first.'))
        self.write({'status': 'draft', 'reviewed_by': False,
                    'reviewed_at': False})
