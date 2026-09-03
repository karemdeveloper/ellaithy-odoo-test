from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from ..models.hr_employee import INACTIVE_TYPE, RESIGNATION_TYPE


class EllithyHrEmployeeStatusWizard(models.TransientModel):
    """Archive an employee, capturing why.

    Reproduces the legacy status-change modal: it collects the inactive type
    and the exit dates, archives the employee, and disables the linked login
    in one step. The date fields are mandatory because the employee model
    enforces the legacy database trigger's rule.
    """

    _name = 'ellithy.hr.employee.status.wizard'
    _description = 'Employee Status Change Wizard'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='cascade')
    currently_active = fields.Boolean(
        related='employee_id.active', string='Currently Active')

    inactive_type = fields.Selection(
        INACTIVE_TYPE, string='Inactive Type', required=True)
    resignation_type = fields.Selection(
        RESIGNATION_TYPE, string='Resignation Type')
    resignation_date = fields.Date(string='Resignation Date', required=True)
    last_working_day = fields.Date(string='Last Working Day', required=True)
    turnover_reason = fields.Text(string='Reason')
    blacklist = fields.Boolean(string='Blacklist this employee')
    blacklist_reason = fields.Text(string='Blacklist Reason')
    disable_login = fields.Boolean(string='Disable login', default=True)

    @api.constrains('resignation_date', 'last_working_day')
    def _check_dates(self):
        for record in self:
            if record.last_working_day < record.resignation_date:
                raise ValidationError(_(
                    'The last working day cannot fall before the '
                    'resignation date.'))

    @api.constrains('blacklist', 'blacklist_reason')
    def _check_blacklist_reason(self):
        for record in self:
            if record.blacklist and not record.blacklist_reason:
                raise ValidationError(
                    _('Blacklisting an employee requires a reason.'))

    def action_apply(self):
        self.ensure_one()
        employee = self.employee_id
        employee.write({
            'inactive_type': self.inactive_type,
            'resignation_type': self.resignation_type,
            'resignation_date': self.resignation_date,
            'last_working_day': self.last_working_day,
            'blacklist': self.blacklist,
            'blacklist_reason': self.blacklist_reason,
            'departure_date': self.last_working_day,
            'departure_description': self.turnover_reason,
            'active': False,
        })
        if self.disable_login and employee.user_id:
            employee.user_id.active = False
        employee.message_post(body=_(
            'Archived as %(type)s. Last working day %(day)s.',
            type=dict(INACTIVE_TYPE).get(self.inactive_type),
            day=self.last_working_day))
        return {'type': 'ir.actions.act_window_close'}

    def action_reactivate(self):
        """Undo an archive, clearing the exit fields the trigger rule forbids
        on an active employee."""
        self.ensure_one()
        employee = self.employee_id
        employee.write({
            'active': True,
            'inactive_type': False,
            'resignation_type': False,
            'resignation_date': False,
            'last_working_day': False,
            'departure_date': False,
        })
        if employee.user_id:
            employee.user_id.active = True
        return {'type': 'ir.actions.act_window_close'}
