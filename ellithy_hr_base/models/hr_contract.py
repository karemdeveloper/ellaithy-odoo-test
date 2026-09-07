from odoo import fields, models

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
        string='Subscription Salary',
        help='Social insurance contribution basis. Often capped separately '
             'from the basic salary.')
    total_wage = fields.Monetary(
        string='Total Salary',
        help='Stored in the legacy system rather than computed -- source '
             'records carry a total above basic plus transport.')
    transportation_allowance = fields.Monetary(string='Transport Allowance')
    other_allowance = fields.Monetary(string='Other Allowance')
    bonus = fields.Monetary(string='Bonus')

    # ---- social insurance ----------------------------------------------
    has_social_insurance = fields.Boolean(string='Has Social Insurance')
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
        help='Whether relatives are covered. The relatives themselves are '
             'listed on the employee, since a dependant belongs to a person '
             'rather than to an engagement.')

    # ---- superseded insurance columns, kept for reference ---------------
    insurance_number = fields.Char(string='Insurance Number (legacy)')
    insurance_office = fields.Char(string='Insurance Office (legacy)')
    insurance_entered_date = fields.Date(string='Insurance Registration Date')
    insurance_salary = fields.Monetary(string='Insured Salary')
    social_insurance_price = fields.Monetary(string='Social Insurance Cost')

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)
