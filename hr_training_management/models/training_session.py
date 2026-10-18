from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

ATTENDANCE_STATUS = [
    ('present', 'Present'),
    ('absent', 'Absent'),
    ('excused', 'Excused'),
]


class TrainingSession(models.Model):
    """One lecture of a training programme.

    Attendance is taken per session, so a trainee's attendance rate is the
    share of the programme's sessions they actually sat in.
    """

    _name = 'training.session'
    _description = 'Training Session'
    _order = 'training_id, date, time_start, sequence, id'

    training_id = fields.Many2one(
        'training.training', string='Training', required=True, index=True,
        ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(string='Session', required=True)
    date = fields.Date(required=True)
    time_start = fields.Float(string='Start Time')
    time_end = fields.Float(string='End Time')
    topic = fields.Char(string='Topic')
    attendance_ids = fields.One2many(
        'training.attendance', 'session_id', string='Attendance')
    present_count = fields.Integer(
        string='Present', compute='_compute_counts', store=True)
    trainee_count = fields.Integer(
        string='Trainees', compute='_compute_counts', store=True)

    @api.depends('attendance_ids.status')
    def _compute_counts(self):
        for session in self:
            session.trainee_count = len(session.attendance_ids)
            session.present_count = len(session.attendance_ids.filtered(
                lambda a: a.status == 'present'))

    @api.constrains('time_start', 'time_end')
    def _check_times(self):
        for session in self:
            if session.time_start and session.time_end \
                    and session.time_end <= session.time_start:
                raise ValidationError(_('A session must end after it starts.'))

    @api.model_create_multi
    def create(self, vals_list):
        sessions = super().create(vals_list)
        sessions._sync_attendance()
        return sessions

    def _sync_attendance(self):
        """One attendance line per trainee, added for newcomers and removed
        for anyone taken off the programme."""
        Attendance = self.env['training.attendance']
        for session in self:
            trainees = session.training_id.employee_ids
            lines = session.attendance_ids
            (lines.filtered(lambda a: a.employee_id not in trainees)).unlink()
            missing = trainees - lines.employee_id
            if missing:
                Attendance.create([{
                    'session_id': session.id, 'employee_id': employee.id,
                } for employee in missing])

    def action_open_attendance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': self.name,
            'res_model': 'training.session', 'res_id': self.id,
            'view_mode': 'form', 'target': 'new',
        }

    def action_mark_all_present(self):
        self.attendance_ids.write({'status': 'present'})

    def action_mark_all_absent(self):
        self.attendance_ids.write({'status': 'absent'})


class TrainingAttendance(models.Model):
    _name = 'training.attendance'
    _description = 'Training Attendance'
    _order = 'session_id, employee_id'

    session_id = fields.Many2one(
        'training.session', string='Session', required=True, index=True,
        ondelete='cascade')
    training_id = fields.Many2one(
        related='session_id.training_id', store=True, index=True)
    session_date = fields.Date(related='session_id.date', store=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Trainee', required=True, index=True,
        ondelete='cascade')
    status = fields.Selection(
        ATTENDANCE_STATUS, string='Status', required=True, default='present')
    note = fields.Char()

    _sql_constraints = [
        ('session_employee_uniq', 'unique(session_id, employee_id)',
         'This trainee is already on the session attendance.'),
    ]
