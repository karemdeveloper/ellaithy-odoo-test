from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

LOAN_STATE = [
    ('draft', 'Draft'),
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('running', 'Running'),
    ('done', 'Repaid'),
    ('cancel', 'Cancelled'),
]


class IbsHrLoan(models.Model):
    """Employee loan or salary advance, repaid by payslip instalment."""

    _name = 'ibs.hr.loan'
    _description = 'Employee Loan'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(
        required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='restrict', tracking=True)
    is_advance = fields.Boolean(
        string='Salary Advance',
        help='An advance is repaid in a single instalment on the next '
             'payslip; a loan is spread over several months.')
    date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True)
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id',
        tracking=True)
    months = fields.Integer(string='Months', default=1, tracking=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)

    installment_amount = fields.Monetary(
        string='Monthly Instalment', compute='_compute_installment',
        store=True, currency_field='currency_id')
    paid_amount = fields.Monetary(
        string='Repaid', compute='_compute_paid', store=True,
        currency_field='currency_id')
    balance = fields.Monetary(
        string='Balance', compute='_compute_paid', store=True,
        currency_field='currency_id')

    line_ids = fields.One2many(
        'ibs.hr.loan.line', 'loan_id', string='Schedule')
    state = fields.Selection(
        LOAN_STATE, default='draft', required=True, tracking=True)
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    @api.constrains('amount', 'months')
    def _check_amount_months(self):
        for record in self:
            if record.amount <= 0:
                raise ValidationError(_('Loan amount must be positive.'))
            if record.months < 1:
                raise ValidationError(_('A loan needs at least one month.'))
            if record.is_advance and record.months != 1:
                raise ValidationError(_(
                    'A salary advance is repaid in a single instalment.'))

    @api.depends('amount', 'months')
    def _compute_installment(self):
        for record in self:
            record.installment_amount = (
                record.amount / record.months if record.months else 0.0)

    @api.depends('line_ids.state', 'line_ids.amount', 'amount')
    def _compute_paid(self):
        for record in self:
            paid = sum(record.line_ids.filtered(
                lambda l: l.state == 'paid').mapped('amount'))
            record.paid_amount = paid
            record.balance = record.amount - paid

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.loan') or _('New')
        return super().create(vals_list)

    def action_approve(self):
        """Approve and build the repayment schedule.

        The last instalment absorbs any rounding remainder so the schedule
        always sums to the loan amount exactly -- otherwise a 1000/3 loan
        leaves a stray 0.01 outstanding forever.
        """
        for record in self:
            if record.state not in ('draft', 'pending'):
                raise ValidationError(_('Only a pending loan can be approved.'))
            record.line_ids.unlink()
            per = record.currency_id.round(record.amount / record.months)
            lines = []
            running = 0.0
            for index in range(record.months):
                last = index == record.months - 1
                value = record.amount - running if last else per
                running += value
                lines.append((0, 0, {
                    'sequence': index + 1,
                    'date': record.date + relativedelta(months=index + 1),
                    'amount': value,
                }))
            record.write({'line_ids': lines, 'state': 'running'})

    def action_cancel(self):
        for record in self:
            unpaid = record.line_ids.filtered(lambda l: l.state != 'paid')
            unpaid.write({'state': 'cancel'})
            record.state = 'cancel'

    def installment_due(self, date_from, date_to):
        """Amount falling due in a payroll period."""
        self.ensure_one()
        due = self.line_ids.filtered(
            lambda l: l.state == 'open' and date_from <= l.date <= date_to)
        return sum(due.mapped('amount')), due


class IbsHrLoanLine(models.Model):
    _name = 'ibs.hr.loan.line'
    _description = 'Loan Instalment'
    _order = 'loan_id, sequence'

    loan_id = fields.Many2one(
        'ibs.hr.loan', required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(default=1)
    date = fields.Date(string='Due Date', required=True, index=True)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='loan_id.currency_id', store=True)
    employee_id = fields.Many2one(
        related='loan_id.employee_id', store=True, index=True)
    state = fields.Selection(
        [('open', 'Open'), ('paid', 'Paid'), ('cancel', 'Cancelled')],
        default='open', required=True)
    payslip_id = fields.Many2one(
        'ibs.hr.payslip', string='Paid On', readonly=True, copy=False,
        ondelete='set null')
