from odoo import _, api, models
from odoo.exceptions import ValidationError
from .hr_payslip import _HCM_WORKFLOW


class PayslipDetailAccess(models.AbstractModel):
    _name = 'ibs.hr.payslip.detail.access'
    _description = 'Payslip detail access'

    def _hcm_check_edit(self, payslips):
        if self.env.su:
            return
        if (self.env.context.get('hcm_workflow') is _HCM_WORKFLOW
                and self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_finance')):
            return
        if not self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_generalist'):
            raise ValidationError(_('Only HR Generalists or HR Admins can edit payroll details.'))
        if any(slip.state == 'done' for slip in payslips):
            raise ValidationError(_('Reset the payslip before editing its details.'))

    @api.model_create_multi
    def create(self, vals_list):
        parent = 'slip_id' if self._name == 'hr.payslip.line' else 'payslip_id'
        for values in vals_list:
            self._hcm_check_edit(self.env['hr.payslip'].browse(values.get(parent)))
        return super().create(vals_list)

    def write(self, vals):
        parent = 'slip_id' if self._name == 'hr.payslip.line' else 'payslip_id'
        self._hcm_check_edit(self.mapped(parent))
        if vals.get(parent):
            self._hcm_check_edit(self.env['hr.payslip'].browse(vals[parent]))
        return super().write(vals)

    def unlink(self):
        parent = 'slip_id' if self._name == 'hr.payslip.line' else 'payslip_id'
        self._hcm_check_edit(self.mapped(parent))
        return super().unlink()


class HrPayslipInput(models.Model):
    _name = 'hr.payslip.input'
    _inherit = ['hr.payslip.input', 'ibs.hr.payslip.detail.access']


class HrPayslipWorkedDays(models.Model):
    _name = 'hr.payslip.worked.days'
    _inherit = ['hr.payslip.worked.days', 'ibs.hr.payslip.detail.access']


class HrPayslipLine(models.Model):
    _name = 'hr.payslip.line'
    _inherit = ['hr.payslip.line', 'ibs.hr.payslip.detail.access']
