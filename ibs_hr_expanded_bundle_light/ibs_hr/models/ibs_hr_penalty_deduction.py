from odoo import api, fields, models


class IbsHrWarningDeduction(models.Model):
    """One month's slice of a penalty, as taken on a payslip.

    CR 2.12 caps disciplinary deductions at five days of pay per month, with
    the remainder carried into following months. A penalty is therefore no
    longer settled by a single payslip, so the link between the two stops
    being a foreign key and becomes a ledger: each row records how many days
    of a given penalty were actually taken on a given payslip.

    Without this, a seven-day penalty could only ever be all-or-nothing.

    The payslip it points at is the standard ``hr.payslip`` from
    ``hr_payroll_community``; the custom ``ibs.hr.payslip`` engine it was
    first written against has been withdrawn.
    """

    _name = 'ibs.hr.warning.deduction'
    _description = 'Penalty Deduction Line'
    _order = 'payslip_id, warning_id'

    warning_id = fields.Many2one(
        'ibs.hr.warning', string='Penalty', required=True, index=True,
        ondelete='cascade')
    payslip_id = fields.Many2one(
        'hr.payslip', string='Payslip', required=True, index=True,
        ondelete='cascade')
    employee_id = fields.Many2one(
        related='warning_id.employee_id', store=True, index=True)
    days = fields.Float(string='Days Taken', digits=(6, 2), required=True)
    amount = fields.Monetary(
        string='Amount', required=True, currency_field='currency_id')
    currency_id = fields.Many2one(
        related='warning_id.currency_id', store=True)
    date = fields.Date(
        string='Deducted On', related='payslip_id.date_to', store=True)

    _sql_constraints = [
        ('warning_payslip_uniq', 'unique(warning_id, payslip_id)',
         'This penalty is already deducted once on that payslip.'),
    ]

    @api.model
    def monthly_cap_days(self):
        """Maximum days of penalty deductible in one month.

        Five days is the Egyptian Labour Law ceiling and the figure confirmed
        in the requirements session, but it is exposed as a parameter because
        it is a policy number, not a constant.
        """
        param = self.env['ir.config_parameter'].sudo().get_param(
            'ibs_hr.max_penalty_days_per_month', '5')
        try:
            return float(param)
        except (TypeError, ValueError):
            return 5.0
