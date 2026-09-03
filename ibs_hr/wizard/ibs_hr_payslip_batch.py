from odoo import _, fields, models
from odoo.exceptions import ValidationError


class IbsHrPayslipBatch(models.TransientModel):
    """Generate and compute payslips for many employees at once."""

    _name = 'ibs.hr.payslip.batch'
    _description = 'Payslip Batch'

    salary_year = fields.Integer(
        required=True, default=lambda self: fields.Date.context_today(self).year)
    salary_month = fields.Integer(
        required=True,
        default=lambda self: fields.Date.context_today(self).month)
    branch_id = fields.Many2one('ellithy.branch', string='Branch')
    department_id = fields.Many2one('hr.department', string='Department')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    calculation_days = fields.Float(string='Calculation Days', default=30.0)

    def _target_employees(self):
        if self.employee_ids:
            return self.employee_ids
        domain = [('active', '=', True)]
        if self.branch_id:
            domain.append(('branch_id', '=', self.branch_id.id))
        if self.department_id:
            domain.append(('department_id', '=', self.department_id.id))
        return self.env['hr.employee'].search(domain)

    def action_generate(self):
        self.ensure_one()
        employees = self._target_employees()
        if not employees:
            raise ValidationError(_('No employees match those filters.'))
        payslip_model = self.env['ibs.hr.payslip']
        created = payslip_model.browse()
        skipped = []
        for employee in employees:
            existing = payslip_model.search([
                ('employee_id', '=', employee.id),
                ('salary_year', '=', self.salary_year),
                ('salary_month', '=', self.salary_month),
            ], limit=1)
            if existing:
                skipped.append(employee.name)
                continue
            if not employee._ibs_contract_on(fields.Date.to_date(
                    f'{self.salary_year}-{self.salary_month:02d}-01')):
                skipped.append(employee.name)
                continue
            created |= payslip_model.create({
                'employee_id': employee.id,
                'salary_year': self.salary_year,
                'salary_month': self.salary_month,
                'calculation_days': self.calculation_days,
            })
        created.action_compute()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payslips %(month)s/%(year)s',
                      month=self.salary_month, year=self.salary_year),
            'res_model': 'ibs.hr.payslip',
            'view_mode': 'list,form',
            'domain': [('id', 'in', created.ids)],
        }
