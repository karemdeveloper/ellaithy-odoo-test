from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo import _

PAYOUT_METHOD = [
    ('bank', 'Bank Account'),
    ('fawry', 'Fawry'),
]


class EllithyHrAccount(models.Model):
    """Salary payout destination.

    The legacy holds three parallel column sets on ``users``: a primary bank
    account, a secondary one, and a Fawry route keyed on national ID and
    phone for staff without a bank account. One child model with a method
    selector replaces all three.
    """

    _name = 'ellithy.hr.account'
    _inherit = ['ellithy.employee.child.audit']
    _description = 'Employee Payout Account'
    _order = 'employee_id, is_primary desc, id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade',
        index=True)
    method = fields.Selection(
        PAYOUT_METHOD, string='Method', required=True, default='bank')
    is_primary = fields.Boolean(string='Primary')

    bank_name = fields.Char(string='Bank Name')
    account_holder = fields.Char(string='Account Holder')
    account_number = fields.Char(string='Account Number')
    account_iban = fields.Char(string='IBAN')
    branch_code = fields.Char(string='Branch Code')
    account_type = fields.Selection(
        [('saving', 'Saving'), ('current', 'Current'), ('salary', 'Salary')],
        string='Account Type')

    fawry_national_number = fields.Char(string='Fawry National ID')
    fawry_phone_number = fields.Char(string='Fawry Phone')

    legacy_slot = fields.Char(
        string='Legacy Slot', copy=False,
        help='bank, bank2 or fawry -- the column block this row came from.')

    @api.constrains('method', 'account_number', 'fawry_national_number')
    def _check_required_by_method(self):
        for record in self:
            if record.method == 'bank' and not record.account_number:
                raise ValidationError(
                    _('A bank payout needs an account number.'))
            if record.method == 'fawry' and not record.fawry_national_number:
                raise ValidationError(
                    _('A Fawry payout needs a national ID number.'))

    @api.constrains('is_primary')
    def _check_single_primary(self):
        for record in self.filtered('is_primary'):
            others = self.search_count([
                ('employee_id', '=', record.employee_id.id),
                ('is_primary', '=', True),
                ('id', '!=', record.id),
            ])
            if others:
                raise ValidationError(_(
                    '%(name)s already has a primary payout account.',
                    name=record.employee_id.name))
