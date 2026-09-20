from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class IbsHrMobileDeduction(models.Model):
    _name = 'ibs.hr.mobile.deduction'
    _description = 'Mobile Invoice Deduction'
    _inherit = ['mail.thread', 'ellithy.hr.action.notification']
    _order = 'period desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='restrict')
    period = fields.Date(
        required=True, help='Use the first day of the payroll month.')
    reference = fields.Char(required=True)
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)
    state = fields.Selection([
        ('draft', 'Draft'), ('approved', 'Approved'), ('deducted', 'Deducted'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='draft')
    payslip_id = fields.Many2one('hr.payslip', readonly=True, ondelete='restrict')

    _sql_constraints = [
        ('employee_period_unique', 'unique(employee_id, period)',
         'Only one mobile invoice can replace the default in a payroll month.'),
        ('amount_nonnegative', 'check(amount >= 0)',
         'The mobile deduction cannot be negative.'),
    ]

    def unlink(self):
        if not self.env.su and any(record.state not in ('draft',) for record in self):
            raise ValidationError(_('Only draft documents can be deleted.'))
        return super().unlink()

    def action_approve(self):
        if not self.env.su and not self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_generalist'):
            raise ValidationError(_('Only HR Generalists or HR Admins can approve an invoice.'))
        for deduction in self:
            if deduction.state != 'draft':
                raise UserError(_('Only a draft invoice can be approved.'))
            if deduction.period.day != 1:
                raise ValidationError(_('Period must be the first day of a month.'))
            deduction._set_state('approved')
            deduction._notify_employee(_('Mobile invoice approved'))

    def action_cancel(self):
        if not self.env.su and not self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_generalist'):
            raise ValidationError(_('Only HR Generalists or HR Admins can cancel an invoice.'))
        for deduction in self:
            if deduction.state == 'deducted':
                raise UserError(_('A deducted invoice must be reversed through payroll.'))
            deduction._set_state('cancelled')
            deduction._notify_employee(_('Mobile invoice cancelled'))

    def _set_state(self, state):
        return super(IbsHrMobileDeduction, self).write({'state': state})

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su and any(values.get('state', 'draft') != 'draft'
                                  or values.get('payslip_id') for values in vals_list):
            raise ValidationError(_('Create a draft invoice and use the approval actions.'))
        records = super().create(vals_list)
        records._notify_approval_group('ibs_hr_payroll.ibs_hr_payroll_generalist',
                                      _('Mobile invoice awaiting approval'))
        return records

    def write(self, vals):
        if not self.env.su:
            if {'state', 'payslip_id'}.intersection(vals):
                raise ValidationError(_('Use the workflow actions to change status.'))
            if {'employee_id', 'period', 'reference', 'amount'}.intersection(vals) and any(
                    record.state != 'draft' for record in self):
                raise ValidationError(_('An approved invoice cannot be edited.'))
        return super().write(vals)
