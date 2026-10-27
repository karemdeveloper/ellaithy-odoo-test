from odoo import _, api, fields, models
from odoo.exceptions import UserError


class IbsHrShiftAssignWizard(models.TransientModel):
    """HR letter item 16: put many employees on a shift in one go."""

    _name = 'ibs.hr.shift.assign.wizard'
    _description = 'Assign Shift'

    shift_id = fields.Many2one('ibs.hr.shift', string='Shift', required=True)
    department_id = fields.Many2one(
        'hr.department', string='Add Department',
        help='Adds every active employee of this department and its sections.')
    branch_id = fields.Many2one('ellithy.branch', string='Add Branch')
    employee_ids = fields.Many2many('hr.employee', string='Employees')
    only_without_shift = fields.Boolean(
        string='Skip Employees Who Have a Shift',
        help='Leave employees who already have a shift as they are.')
    regenerate = fields.Boolean(
        string='Recompute This Month', default=True,
        help="Rebuild this month's attendance days of these employees with "
             "the new shift.")

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if (self.env.context.get('active_model') == 'hr.employee'
                and self.env.context.get('active_ids')):
            values['employee_ids'] = [(6, 0, self.env.context['active_ids'])]
        return values

    @api.onchange('department_id', 'branch_id')
    def _onchange_add_group(self):
        domain = [('active', '=', True)]
        if self.department_id:
            found = self.env['hr.employee'].search(
                domain + [('department_id', 'child_of', self.department_id.id)])
            self.employee_ids |= found
            self.department_id = False
        if self.branch_id:
            found = self.env['hr.employee'].search(
                domain + [('branch_id', '=', self.branch_id.id)])
            self.employee_ids |= found
            self.branch_id = False

    def action_assign(self):
        self.ensure_one()
        employees = self.employee_ids
        if self.only_without_shift:
            employees = employees.filtered(lambda e: not e.shift_id)
        if not employees:
            raise UserError(_('Choose at least one employee to assign.'))
        employees.write({'shift_id': self.shift_id.id})
        if self.regenerate:
            self.env['ibs.hr.attendance.day']._generate_current_month(
                employees=employees)
        return {
            'type': 'ir.actions.client', 'tag': 'display_notification',
            'params': {
                'type': 'success',
                'message': _('%(count)s employees assigned to %(shift)s.',
                             count=len(employees), shift=self.shift_id.name),
                'next': {'type': 'ir.actions.act_window_close'},
            },
        }
