from odoo import _, api, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    payslip_ids = fields.One2many(
        'ibs.hr.payslip', 'employee_id', string='Payslips')
    warning_ids = fields.One2many(
        'ibs.hr.warning', 'employee_id', string='Warnings')
    loan_ids = fields.One2many(
        'ibs.hr.loan', 'employee_id', string='Loans')
    attendance_day_ids = fields.One2many(
        'ibs.hr.attendance.day', 'employee_id', string='Attendance Days')

    open_loan_balance = fields.Monetary(
        string='Open Loan Balance', compute='_compute_open_loan_balance',
        currency_field='currency_id')
    warning_count = fields.Integer(
        string='Warning Count', compute='_compute_warning_count')
    investigation_line_ids = fields.One2many(
        'ibs.hr.investigation.employee', 'employee_id',
        string='Investigations')
    investigation_count = fields.Integer(
        string='Investigation Count', compute='_compute_investigation_count')

    def _ibs_contract_on(self, date):
        """The contract covering a date.

        Payroll must read the contract that was in force during the period,
        not whichever one happens to be current -- otherwise recomputing an
        old payslip silently applies today's salary.
        """
        # An empty recordset is a legitimate input, not a programming error:
        # every compute that reaches this runs once on a blank form before the
        # user has picked anyone. Return "no contract" rather than raising.
        if not self:
            return self.env['hr.contract']
        self.ensure_one()
        if not date:
            return self.env['hr.contract']
        contracts = self.env['hr.contract'].search([
            ('employee_id', '=', self.id),
            ('date_start', '<=', date),
            '|', ('date_end', '=', False), ('date_end', '>=', date),
        ], order='date_start desc', limit=1)
        if contracts:
            return contracts
        return self.env['hr.contract'].search(
            [('employee_id', '=', self.id)], order='date_start desc', limit=1)

    @api.depends('loan_ids.balance', 'loan_ids.state')
    def _compute_open_loan_balance(self):
        for record in self:
            record.open_loan_balance = sum(record.loan_ids.filtered(
                lambda l: l.state == 'running').mapped('balance'))

    def _compute_warning_count(self):
        data = self.env['ibs.hr.warning']._read_group(
            [('employee_id', 'in', self.ids), ('status', '=', 'approved')],
            ['employee_id'], ['__count'])
        mapped = {employee.id: count for employee, count in data}
        for record in self:
            record.warning_count = mapped.get(record.id, 0)

    def _compute_investigation_count(self):
        data = self.env['ibs.hr.investigation.employee']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        mapped = {employee.id: count for employee, count in data}
        for record in self:
            record.investigation_count = mapped.get(record.id, 0)

    def action_view_warnings(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Violations - %(name)s', name=self.name),
            'res_model': 'ibs.hr.warning',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }

    def action_view_investigations(self):
        self.ensure_one()
        investigations = self.investigation_line_ids.mapped('investigation_id')
        return {
            'type': 'ir.actions.act_window',
            'name': _('Investigations - %(name)s', name=self.name),
            'res_model': 'ibs.hr.investigation',
            'view_mode': 'list,form',
            'domain': [('id', 'in', investigations.ids)],
        }
