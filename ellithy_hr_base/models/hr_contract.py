from odoo import fields, models


class HrContract(models.Model):
    """Contract.

    Salary and insurance amounts live here rather than on the employee so a
    raise leaves the previous figures intact. ``wage`` is stock and carries
    the legacy ``basic_salary``.
    """

    _inherit = 'hr.contract'

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
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)
