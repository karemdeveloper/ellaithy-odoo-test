from odoo import api, fields, models


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
