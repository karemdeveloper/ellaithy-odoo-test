from odoo import _, fields, models


class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    training_participant_ids = fields.One2many(
        'training.participant', 'employee_id', string='Training History',
        groups='hr.group_hr_user')
    training_count = fields.Integer(
        compute='_compute_training_count', groups='hr.group_hr_user')

    def _compute_training_count(self):
        data = self.env['training.participant']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        counts = {employee.id: count for employee, count in data}
        for employee in self:
            employee.training_count = counts.get(employee.id, 0)

    def action_view_training_history(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Training History - %(name)s', name=self.name),
            'res_model': 'training.participant',
            'view_mode': 'list,form',
            'domain': [('employee_id', '=', self.id)],
            'context': {'create': False},
        }
