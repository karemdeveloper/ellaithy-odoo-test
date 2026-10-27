from odoo import fields, models


class IbsHrPayrollSource(models.Model):
    _name = 'ibs.hr.payroll.source'
    _description = 'Consumed HCM Payroll Source'

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='restrict')
    period = fields.Date(required=True, index=True)
    code = fields.Char(required=True, index=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)
    payslip_id = fields.Many2one(
        'hr.payslip', required=True, ondelete='cascade', index=True)

    _sql_constraints = [
        ('employee_period_code_unique', 'unique(employee_id, period, code)',
         'This monthly HCM payroll source has already been consumed.'),
    ]

