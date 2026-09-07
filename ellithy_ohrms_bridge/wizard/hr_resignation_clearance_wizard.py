from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class HrResignationClearanceWizard(models.TransientModel):
    """Start a clearance: confirm the last day, choose who has to sign.

    Two decisions are taken together here because they are taken together in
    practice. HR settles the leaving date, and in the same breath works out
    which departments the person owes something to. Doing it in a wizard
    rather than on the resignation form means the departments are chosen
    once, deliberately, and the form cannot be half-filled and forgotten.
    """

    _name = 'hr.resignation.clearance.wizard'
    _description = 'Start Clearance'

    resignation_id = fields.Many2one(
        'hr.resignation', string='Resignation', required=True,
        ondelete='cascade')
    employee_id = fields.Many2one(
        related='resignation_id.employee_id', string='Employee')
    employee_department_id = fields.Many2one(
        related='resignation_id.employee_id.department_id',
        string="Employee's Department")

    last_working_day = fields.Date(
        string='Last Working Day', required=True,
        compute='_compute_last_working_day', store=True, readonly=False,
        # Without precompute the value is written after the INSERT, and the
        # required flag's NOT NULL rejects the row first.
        precompute=True,
        help='Confirmed here rather than assumed: starting clearance is the '
             'point at which the date stops being a proposal. It is written '
             'back to the resignation.')
    department_ids = fields.Many2many(
        'hr.department', string='Departments to Clear', required=True,
        help='Each department chosen gets its own line to sign. They may '
             'sign in any order; all of them must sign before clearance can '
             'be confirmed.')
    note = fields.Text(string='Instructions')

    @api.depends('resignation_id')
    def _compute_last_working_day(self):
        for wizard in self:
            resignation = wizard.resignation_id
            wizard.last_working_day = (
                resignation.approved_revealing_date
                or resignation.expected_revealing_date)

    @api.constrains('last_working_day', 'resignation_id')
    def _check_last_working_day(self):
        for wizard in self:
            joined = wizard.resignation_id.joined_date
            if joined and wizard.last_working_day < joined:
                raise ValidationError(_(
                    'The last working day cannot fall before the joining '
                    'date (%(joined)s).', joined=joined))

    def action_start_clearance(self):
        """Write the date back, raise a line per department."""
        self.ensure_one()
        resignation = self.resignation_id
        if resignation.request_type != 'exit':
            raise ValidationError(
                _('Clearance applies to an exit, not to a suspension.'))
        if resignation.state not in ('confirm', 'endorsed'):
            raise ValidationError(_(
                'Clearance starts once the resignation has been confirmed, '
                'and before it is approved.'))

        resignation.write({
            'expected_revealing_date': self.last_working_day,
            'clearance_state': 'progress',
        })

        # Only departments not already on the form: restarting clearance to
        # add one more must not wipe the signatures already collected.
        existing = resignation.clearance_line_ids.department_id
        Clearance = self.env['hr.resignation.clearance']
        for index, department in enumerate(self.department_ids - existing):
            Clearance.create({
                'resignation_id': resignation.id,
                'department_id': department.id,
                'sequence': (index + 1) * 10,
                'note': self.note,
            })
        resignation.message_post(body=_(
            'Clearance started for %(count)s department(s). Last working '
            'day confirmed as %(day)s.',
            count=len(self.department_ids), day=self.last_working_day))
        return resignation.action_view_clearance()
