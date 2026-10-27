from datetime import date

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

MEDICAL_TIER = [
    ('a', 'A'),
    ('b', 'B'),
    ('c', 'C'),
]


class HrContract(models.Model):
    """Contract.

    Salary and insurance live here rather than on the employee so a raise or
    a renewal leaves the previous figures intact. ``wage`` is stock and
    carries the legacy ``basic_salary``.

    Insurance moved here from ``hr.employee``: the subscription salary a
    contribution is calculated on, the medical tier and its costs, and the
    office an employee is registered at are all terms of an engagement, and
    they change when the engagement changes. Holding them on the employee
    meant renewing a contract silently rewrote the figures the old one was
    filed under. The employee still shows them, read-only, from the running
    contract.
    """

    _inherit = 'hr.contract'

    # ---- salary ---------------------------------------------------------
    subscription_wage = fields.Monetary(
        string='Insurance Salary',
        help='Social insurance contribution basis. Often capped separately '
             'from the basic salary.')
    total_wage = fields.Monetary(
        string='Total Salary',
        help='Stored in the legacy system rather than computed -- source '
             'records carry a total above basic plus transport.')
    transportation_allowance = fields.Monetary(string='Transport Allowance')
    transportation_allowance_daily = fields.Monetary(
        string='Transportation Allowance per Day')
    employment_allowance = fields.Monetary(string='Employment Allowance')
    commitment_allowance = fields.Monetary(string='Commitment Allowance')
    other_allowance = fields.Monetary(string='Other Allowance')
    bonus = fields.Monetary(string='Bonus')
    mobile_invoice_deduction = fields.Monetary(
        string='Mobile Invoice Deduction')

    # ---- social insurance ----------------------------------------------
    has_social_insurance = fields.Boolean(string='Has Social Insurance')
    social_insurance_percentage = fields.Float(
        string='Social Insurance Percentage', default=11.25, digits=(5, 2))
    social_insurance_amount = fields.Monetary(
        string='Social Insurance Amount', compute='_compute_social_insurance_amount',
        store=True)
    social_insurance_office_id = fields.Many2one(
        'ellithy.hr.insurance.office', string='Social Insurance Office',
        ondelete='restrict')
    social_insurance_number = fields.Char(
        string='Social Insurance Number',
        help='Legacy users.social_insurance_number. Distinct from the older '
             'insurance_number column, which is kept below.')
    social_insurance_start_date = fields.Date(
        string='Social Insurance Start Date',
        help='When insured service began. Read by the annual leave rule: ten '
             'years of insured service raises the entitlement to 30 days, and '
             'insured service is portable between employers.')

    # ---- medical insurance ---------------------------------------------
    medical_insurance_type = fields.Selection(
        MEDICAL_TIER, string='Medical Insurance Type')
    medical_insurance_date = fields.Date(string='Medical Insurance Date')
    medical_card_number = fields.Char(string='Medical Card Number')
    medical_cost_per_year = fields.Monetary(string='Cost Per Year')
    medical_cost_per_month = fields.Monetary(string='Cost Per Month')
    medical_employee_share = fields.Float(
        string='Employee Share (%)', digits=(5, 2))
    has_medical_relative = fields.Boolean(
        string='Has Covered Relatives',
        help='Whether relatives are covered.')

    # The list itself belongs to the person, not to the engagement, so it is
    # stored on the employee. It is reachable from here because the medical
    # tier and the relatives it covers are decided in the same conversation:
    # writable, so a relative added while filing the contract lands on the
    # employee rather than being dropped. One list, two doors -- editing it
    # here and editing it on the employee file are the same edit.
    dependant_ids = fields.One2many(
        related='employee_id.dependant_ids', readonly=False,
        string='Covered Relatives')

    # ---- superseded insurance columns, kept for reference ---------------
    insurance_number = fields.Char(string='Insurance Number (legacy)')
    insurance_office = fields.Char(string='Insurance Office (legacy)')
    insurance_entered_date = fields.Date(string='Insurance Registration Date')
    insurance_salary = fields.Monetary(string='Insured Salary')
    social_insurance_price = fields.Monetary(string='Social Insurance Cost')

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    # ---- contract follow-up -------------------------------------------
    # An ended contract only needs action if it is the employee's newest one
    # and the employee is still working; an older ended contract has already
    # been renewed, and a leaver's contract needs nothing.
    is_last_contract = fields.Boolean(
        string='Latest Contract', compute='_compute_is_last_contract',
        store=True, index=True)
    employee_active = fields.Boolean(
        related='employee_id.active', store=True, string='Employee Active')
    days_to_end = fields.Integer(
        string='Days Left', compute='_compute_days_to_end',
        help='Days until the contract ends; negative once it has ended.')

    @api.depends('employee_id.contract_ids.date_start',
                 'employee_id.contract_ids.state')
    def _compute_is_last_contract(self):
        for contract in self:
            siblings = contract.employee_id.contract_ids.filtered(
                lambda c: c.state != 'cancel')
            latest = max(siblings, key=lambda c: (c.date_start or date.min, c.id)) \
                if siblings else False
            contract.is_last_contract = latest == contract

    @api.model
    def get_import_templates(self):
        return [{
            'label': _('Import Template for Contracts (Ellaithy)'),
            'template': '/ellithy_hr_base/static/xls/contracts_import_template.xlsx',
        }]

    @api.depends('date_end')
    def _compute_days_to_end(self):
        today = fields.Date.context_today(self)
        for contract in self:
            contract.days_to_end = (
                (contract.date_end - today).days if contract.date_end else 0)

    @api.depends('has_social_insurance', 'subscription_wage',
                 'social_insurance_percentage', 'currency_id')
    def _compute_social_insurance_amount(self):
        for contract in self:
            amount = 0.0
            if contract.has_social_insurance:
                amount = (contract.subscription_wage
                          * contract.social_insurance_percentage / 100.0)
            contract.social_insurance_amount = contract.currency_id.round(amount)

    @api.constrains(
        'transportation_allowance_daily', 'employment_allowance',
        'commitment_allowance', 'other_allowance',
        'mobile_invoice_deduction', 'subscription_wage',
        'social_insurance_percentage')
    def _check_hcm_amounts(self):
        for contract in self:
            monetary_values = (
                contract.transportation_allowance_daily,
                contract.employment_allowance,
                contract.commitment_allowance,
                contract.other_allowance,
                contract.mobile_invoice_deduction,
                contract.subscription_wage,
            )
            if any(value < 0 for value in monetary_values):
                raise ValidationError(_('Salary amounts cannot be negative.'))
            if not 0.0 <= contract.social_insurance_percentage <= 100.0:
                raise ValidationError(
                    _('Social Insurance Percentage must be between 0 and 100.'))
