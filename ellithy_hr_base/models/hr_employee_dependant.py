from odoo import api, fields, models

MEDICAL_TIER = [('a', 'A'), ('b', 'B'), ('c', 'C')]


class EllithyHrDependant(models.Model):
    """Medical insurance dependant.

    The legacy carries two fixed blocks of eleven columns each
    (``relative_*`` and ``relative_*_2``) directly on ``users``. Normalising
    them here removes the hardcoded limit of two and makes dependants
    reportable.
    """

    _name = 'ellithy.hr.dependant'
    _inherit = ['ellithy.employee.child.audit']
    _description = 'Employee Medical Dependant'
    _order = 'employee_id, id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade',
        index=True)
    company_id = fields.Many2one(
        related='employee_id.company_id', store=True)
    currency_id = fields.Many2one(
        related='employee_id.currency_id', store=True)

    name = fields.Char(string='Relative Name', required=True)
    relation = fields.Char(string='Relation')
    card_number = fields.Char(string='Card Number')
    code = fields.Char(string='Relative Code')
    medical_insurance_type = fields.Selection(
        MEDICAL_TIER, string='Medical Insurance Type')
    insurance_date = fields.Date(string='Insurance Date')
    birthday = fields.Date(string='Date of Birth')
    age = fields.Integer(string='Age', compute='_compute_age', store=True)
    overage_price = fields.Monetary(
        string='Overage Price', currency_field='currency_id')
    cost_per_year = fields.Monetary(
        string='Cost Per Year', currency_field='currency_id')
    cost_per_month = fields.Monetary(
        string='Cost Per Month', currency_field='currency_id')
    employee_share = fields.Float(string='Employee Share (%)', digits=(5, 2))

    legacy_slot = fields.Integer(
        string='Legacy Slot', copy=False,
        help='1 or 2, matching the relative_* column block this row came from.')

    @api.depends('birthday')
    def _compute_age(self):
        today = fields.Date.context_today(self)
        for record in self:
            if not record.birthday:
                record.age = 0
                continue
            born = record.birthday
            record.age = today.year - born.year - (
                (today.month, today.day) < (born.month, born.day))
