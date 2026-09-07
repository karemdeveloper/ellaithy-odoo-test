from odoo import _, api, fields, models


class HrEmployee(models.Model):
    """Reconcile the two definitions of ``joining_date``.

    ``hr_employee_updation`` computes the field from the earliest contract
    start date. That is reasonable for an employee hired inside Odoo, but
    destructive for a migrated one: the legacy platform recorded a joining
    date for 1,228 employees, only 202 of whom have a contract, and the
    compute fires on ``contract_id`` -- so creating a contract for any of the
    other 1,026 would overwrite a real date with the contract's start date.

    The override keeps the migrated value and only computes when the field is
    empty, so both behaviours coexist.
    """

    _inherit = 'hr.employee'

    joining_date = fields.Date(
        compute='_compute_joining_date', store=True, readonly=False,
        help='Date the employee joined. Migrated from the legacy platform '
             'where available; otherwise derived from the earliest contract.')

    @api.depends('contract_id')
    def _compute_joining_date(self):
        for employee in self:
            if employee.joining_date:
                # Already known -- never overwrite it from a contract.
                continue
            starts = employee.contract_ids.mapped('date_start')
            employee.joining_date = min(starts) if starts else False


class HrEmployeeResignation(models.Model):
    """CR 2.7 -- reach the resignation from the employee, do not restate it.

    The requirement is that resignation is handled on one screen. Rather than
    copying the dates and reasons onto the employee form, where they would
    drift out of step with the record that owns them, the employee carries a
    smart button that opens the resignation itself.
    """

    _inherit = 'hr.employee'

    # ``hr.loan`` is an OpenHRMS model, so the relation to it belongs here
    # rather than in ibs_hr, which cannot see it.
    loan_ids = fields.One2many(
        'hr.loan', 'employee_id', string='Loans')
    open_loan_balance = fields.Monetary(
        string='Open Loan Balance', compute='_compute_open_loan_balance',
        currency_field='currency_id')

    resignation_ids = fields.One2many(
        'hr.resignation', 'employee_id', string='Resignations')
    resignation_count = fields.Integer(
        string='Resignation Count', compute='_compute_resignation_count')

    @api.depends('loan_ids.balance_amount', 'loan_ids.state')
    def _compute_open_loan_balance(self):
        for employee in self:
            employee.open_loan_balance = sum(employee.loan_ids.filtered(
                lambda loan: loan.state == 'approve').mapped(
                    'balance_amount'))

    def _compute_resignation_count(self):
        data = self.env['hr.resignation']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        mapped = {employee.id: count for employee, count in data}
        for employee in self:
            employee.resignation_count = mapped.get(employee.id, 0)

    def action_view_resignations(self):
        self.ensure_one()
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Resignation - %(name)s', name=self.name),
            'res_model': 'hr.resignation',
            'domain': [('employee_id', '=', self.id)],
            'context': {'default_employee_id': self.id},
        }
        resignations = self.resignation_ids
        if len(resignations) == 1:
            action.update({'view_mode': 'form', 'res_id': resignations.id})
        else:
            action['view_mode'] = 'list,form'
        return action
