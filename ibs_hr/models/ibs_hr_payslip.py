import calendar

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SLIP_STATE = [
    ('draft', 'Draft'),
    ('computed', 'Computed'),
    ('confirmed', 'Confirmed'),
    ('paid', 'Paid'),
    ('cancel', 'Cancelled'),
]

# Component sets, mirroring the legacy user_payroll_summaries columns.
ALLOWANCE_FIELDS = [
    'base_salary', 'overtime', 'transportation_allowance', 'bonus', 'kpi',
    'other_allowance',
]
DEDUCTION_FIELDS = [
    'absence_penalty', 'late_penalty', 'early_leave_penalty',
    'unachieved_hours_penalty', 'misconduct_penalty',
    'single_fingerprint_penalty', 'deduction_leave', 'mobile_deduction',
    'medical_deduction', 'loan', 'extra_deduction', 'id_card_deduction',
    'admin_penalty', 'insurance_employee_share',
]

DAYS_IN_MONTH_BASIS = 30.0
INSURANCE_EMPLOYEE_RATE = 0.11


class IbsHrPayslip(models.Model):
    """Monthly payslip.

    Component names and arithmetic follow the legacy `user_payroll_summaries`
    table. Two deliberate departures from the legacy behaviour, both of which
    are legacy defects rather than rules:

    1. `insurance_employee_share` is ALWAYS included in `total_deduction`.
       The legacy includes it on 5,112 of 9,976 rows and omits it on 3,408,
       with no discernible rule. Including it always is the only consistent
       reading, and it matches the majority.

    2. `absence_days` here is a real day count. The legacy column of the same
       name stores a money value identical to `absence_penalty` on 2,915 of
       3,174 rows -- a mis-named column that will silently corrupt any
       migration that trusts it.

    Roughly 1,456 legacy rows do not reconcile to their own line items at all.
    Historical payslips are therefore useful for validating this engine, but
    are not a specification for it.
    """

    _name = 'ibs.hr.payslip'
    _description = 'Payslip'
    _inherit = ['mail.thread']
    _order = 'salary_year desc, salary_month desc, employee_id'

    name = fields.Char(
        required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    department_id = fields.Many2one(
        related='employee_id.department_id', store=True)
    contract_id = fields.Many2one(
        'hr.contract', string='Contract', readonly=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)

    salary_year = fields.Integer(string='Year', required=True)
    salary_month = fields.Integer(string='Month', required=True)
    date_from = fields.Date(string='From', compute='_compute_dates', store=True)
    date_to = fields.Date(string='To', compute='_compute_dates', store=True)

    calculation_days = fields.Float(
        string='Calculation Days', default=DAYS_IN_MONTH_BASIS,
        help='Divisor for the daily rate. The legacy system uses 30 '
             'regardless of calendar month length -- verified across 3,174 '
             'penalty rows.')
    daily_rate = fields.Monetary(
        string='Daily Rate', compute='_compute_daily_rate', store=True,
        currency_field='currency_id')

    # ---- allowances -------------------------------------------------
    base_salary = fields.Monetary(currency_field='currency_id')
    overtime = fields.Monetary(currency_field='currency_id')
    transportation_allowance = fields.Monetary(currency_field='currency_id')
    bonus = fields.Monetary(currency_field='currency_id')
    kpi = fields.Monetary(currency_field='currency_id')
    other_allowance = fields.Monetary(currency_field='currency_id')
    joining_difference = fields.Monetary(
        currency_field='currency_id',
        help='Pro-rata adjustment for a mid-month joiner. Recorded but NOT '
             'summed into total allowance -- matching the legacy, where 9,504 '
             'of 9,976 rows exclude it.')
    resignation_difference = fields.Monetary(
        currency_field='currency_id',
        help='Pro-rata adjustment for a mid-month leaver. Excluded from the '
             'total for the same reason as joining_difference.')
    total_allowance = fields.Monetary(
        compute='_compute_totals', store=True, currency_field='currency_id')

    # ---- deductions -------------------------------------------------
    absence_days = fields.Float(string='Absence (days)', digits=(6, 2))
    absence_penalty = fields.Monetary(currency_field='currency_id')
    late_penalty = fields.Monetary(currency_field='currency_id')
    early_leave_penalty = fields.Monetary(currency_field='currency_id')
    unachieved_hours_penalty = fields.Monetary(currency_field='currency_id')
    misconduct_penalty = fields.Monetary(currency_field='currency_id')
    single_fingerprint_penalty = fields.Monetary(currency_field='currency_id')
    deduction_leave = fields.Monetary(currency_field='currency_id')
    mobile_deduction = fields.Monetary(currency_field='currency_id')
    medical_deduction = fields.Monetary(currency_field='currency_id')
    loan = fields.Monetary(currency_field='currency_id')
    extra_deduction = fields.Monetary(currency_field='currency_id')
    id_card_deduction = fields.Monetary(currency_field='currency_id')
    admin_penalty = fields.Monetary(currency_field='currency_id')
    insurance_employee_share = fields.Monetary(currency_field='currency_id')
    total_deduction = fields.Monetary(
        compute='_compute_totals', store=True, currency_field='currency_id')

    net_salary = fields.Monetary(
        compute='_compute_totals', store=True, currency_field='currency_id',
        tracking=True)

    warning_ids = fields.One2many(
        'ibs.hr.warning', 'payslip_id', string='Penalties Applied')
    loan_line_ids = fields.One2many(
        'ibs.hr.loan.line', 'payslip_id', string='Loan Instalments')

    state = fields.Selection(
        SLIP_STATE, default='draft', required=True, tracking=True)
    compute_log = fields.Text(string='Computation Log', readonly=True)
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('employee_period_uniq',
         'unique(employee_id, salary_year, salary_month)',
         'This employee already has a payslip for that month.'),
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another payslip already carries this legacy ID.'),
    ]

    # ------------------------------------------------------------------
    @api.constrains('salary_month', 'salary_year')
    def _check_period(self):
        for record in self:
            if not 1 <= record.salary_month <= 12:
                raise ValidationError(_('Month must be between 1 and 12.'))
            if not 2000 <= record.salary_year <= 2100:
                raise ValidationError(_('Year looks implausible.'))

    @api.depends('salary_year', 'salary_month')
    def _compute_dates(self):
        for record in self:
            if not (record.salary_year and 1 <= record.salary_month <= 12):
                record.date_from = record.date_to = False
                continue
            last = calendar.monthrange(record.salary_year, record.salary_month)[1]
            record.date_from = fields.Date.to_date(
                f'{record.salary_year}-{record.salary_month:02d}-01')
            record.date_to = fields.Date.to_date(
                f'{record.salary_year}-{record.salary_month:02d}-{last:02d}')

    @api.depends('base_salary', 'calculation_days')
    def _compute_daily_rate(self):
        for record in self:
            basis = record.calculation_days or DAYS_IN_MONTH_BASIS
            record.daily_rate = record.base_salary / basis

    @api.depends(*(ALLOWANCE_FIELDS + DEDUCTION_FIELDS))
    def _compute_totals(self):
        for record in self:
            allowance = sum(record[f] for f in ALLOWANCE_FIELDS)
            deduction = sum(record[f] for f in DEDUCTION_FIELDS)
            record.total_allowance = allowance
            record.total_deduction = deduction
            record.net_salary = allowance - deduction

    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.payslip') or _('New')
        return super().create(vals_list)

    def action_compute(self):
        """Populate every component from the source models."""
        for record in self:
            if record.state in ('confirmed', 'paid'):
                raise ValidationError(_(
                    'A confirmed payslip cannot be recomputed. Reset it first.'))
            record._compute_sheet()
        return True

    def _compute_sheet(self):
        self.ensure_one()
        log = []
        contract = self.employee_id._ibs_contract_on(self.date_to)
        if not contract:
            raise ValidationError(_(
                'No contract covers %(date)s for %(name)s.',
                date=self.date_to, name=self.employee_id.name))
        self.contract_id = contract

        values = {
            'base_salary': contract.wage,
            'transportation_allowance': contract.transportation_allowance,
            'other_allowance': contract.other_allowance,
            'bonus': contract.bonus,
        }
        rate = contract.wage / (self.calculation_days or DAYS_IN_MONTH_BASIS)
        log.append(f'daily rate = {contract.wage} / '
                   f'{self.calculation_days or DAYS_IN_MONTH_BASIS} = {rate:.4f}')

        # ---- attendance-derived components
        totals = self.env['ibs.hr.attendance.day'].totals_for_period(
            self.employee_id, self.date_from, self.date_to)
        values['absence_days'] = totals['absence_days']
        values['absence_penalty'] = totals['absence_days'] * rate
        values['overtime'] = totals['overtime_hours'] * (rate / 8.0)
        values['unachieved_hours_penalty'] = (
            totals['shortfall_hours'] * (rate / 8.0))
        values['late_penalty'] = (
            totals['late_minutes'] / 60.0) * (rate / 8.0)
        values['early_leave_penalty'] = (
            totals['early_leave_minutes'] / 60.0) * (rate / 8.0)
        values['single_fingerprint_penalty'] = (
            totals['single_punch_count'] * rate * 0.5)
        log.append(f'attendance: {totals}')

        # ---- discipline
        warnings = self.env['ibs.hr.warning'].search([
            ('employee_id', '=', self.employee_id.id),
            ('status', '=', 'approved'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
            '|', ('payslip_id', '=', False), ('payslip_id', '=', self.id),
        ])
        values['misconduct_penalty'] = sum(warnings.mapped('deducted_amount'))
        log.append(f'discipline: {len(warnings)} warning(s), '
                   f'{values["misconduct_penalty"]:.2f}')

        # ---- loans and advances
        lines = self.env['ibs.hr.loan.line'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'open'),
            ('date', '>=', self.date_from),
            ('date', '<=', self.date_to),
        ])
        values['loan'] = sum(lines.mapped('amount'))
        log.append(f'loans: {len(lines)} instalment(s), {values["loan"]:.2f}')

        # ---- insurance and entitlement costs
        employee = self.employee_id
        if employee.has_social_insurance:
            basis = contract.subscription_wage or contract.wage
            values['insurance_employee_share'] = (
                basis * INSURANCE_EMPLOYEE_RATE)
            log.append(f'insurance: {basis} x {INSURANCE_EMPLOYEE_RATE} = '
                       f'{values["insurance_employee_share"]:.2f}')
        else:
            values['insurance_employee_share'] = 0.0

        values['mobile_deduction'] = (
            employee.mobile_price if employee.has_mobile else 0.0)
        values['medical_deduction'] = (
            employee.medical_price if employee.has_medical else 0.0)

        values['compute_log'] = '\n'.join(log)
        values['state'] = 'computed'
        self.write(values)
        warnings.write({'payslip_id': self.id})
        lines.write({'payslip_id': self.id})

    def action_confirm(self):
        for record in self:
            if record.state != 'computed':
                raise ValidationError(_('Compute the payslip before confirming.'))
            record.loan_line_ids.write({'state': 'paid'})
            record.state = 'confirmed'

    def action_reset(self):
        for record in self:
            record.loan_line_ids.write({'state': 'open'})
            record.warning_ids.write({'payslip_id': False})
            record.loan_line_ids.write({'payslip_id': False})
            record.state = 'draft'

    def action_mark_paid(self):
        self.filtered(lambda r: r.state == 'confirmed').write({'state': 'paid'})
