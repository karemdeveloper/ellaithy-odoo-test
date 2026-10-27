from odoo import _, api, fields, models

DAY_STATE = [
    ('present', 'Present'),
    ('absent', 'Absent'),
    ('leave', 'On Leave'),
    ('weekend', 'Weekend'),
    ('holiday', 'Public Holiday'),
]


class IbsHrAttendanceDay(models.Model):
    """One employee, one day: the derived record payroll consumes.

    Raw punches are noisy -- the legacy `attendances` table holds 149,303 rows
    with cross-midnight shifts, geolocation, and several capture methods. This
    model is the settled interpretation of a day, and it is the ONLY thing
    payroll reads. Keeping the interpretation in one place is what stops the
    payroll engine and the discipline engine disagreeing about whether someone
    was late.
    """

    _name = 'ibs.hr.attendance.day'
    _description = 'Derived Attendance Day'
    _order = 'date desc, employee_id'

    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, index=True,
        ondelete='cascade')
    date = fields.Date(string='Date', required=True, index=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')

    state = fields.Selection(
        DAY_STATE, string='Day State', required=True, default='present')

    check_in = fields.Datetime(string='Check In')
    check_out = fields.Datetime(string='Check Out')
    single_punch = fields.Boolean(
        string='Single Fingerprint', compute='_compute_single_punch',
        store=True,
        help='Exactly one of check in / check out is present. The legacy '
             'system penalises this separately from lateness.')

    scheduled_hours = fields.Float(string='Scheduled Hours', digits=(6, 2))
    worked_hours = fields.Float(
        string='Worked Hours', digits=(6, 2), compute='_compute_worked_hours',
        store=True, readonly=False)

    late_minutes = fields.Integer(string='Late (min)')
    early_leave_minutes = fields.Integer(string='Early Leave (min)')
    shortfall_hours = fields.Float(
        string='Unachieved Hours', digits=(6, 2),
        compute='_compute_shortfall', store=True,
        help='Scheduled minus worked, floored at zero. Feeds the legacy '
             'unachieved_hours_penalty component.')
    overtime_hours = fields.Float(string='Overtime Hours', digits=(6, 2))

    is_paid_leave = fields.Boolean(string='Paid Leave')
    absence_days = fields.Float(
        string='Absence (days)', digits=(6, 2), compute='_compute_absence_days',
        store=True,
        help='A real day count. NOTE: the legacy column of the same name '
             'stores a money value, not days -- see README.')

    # ---- migration provenance ------------------------------------------
    capture_type = fields.Selection(
        [('zk', 'ZKTeco Device'), ('wifi', 'Wi-Fi'), ('import', 'Imported'),
         ('nfc', 'NFC'), ('qr', 'QR'), ('manual', 'Manual')],
        string='Capture Method',
        help='How the punch was recorded. 79% of legacy rows come from ZKTeco '
             'biometric terminals.')
    crossed_midnight = fields.Boolean(
        string='Crossed Midnight', readonly=True,
        help='Check-out time fell before check-in time, so the shift was '
             'treated as ending the following day.')
    legacy_worked_hours = fields.Float(
        string='Legacy Worked Hours', digits=(6, 2), readonly=True,
        help='What the legacy system itself recorded, converted from minutes. '
             'Kept so migrated days can be reconciled against the source '
             'rather than silently restated.')
    worked_hours_variance = fields.Float(
        string='Variance vs Legacy', digits=(6, 2),
        compute='_compute_variance', store=True,
        help='Computed worked hours minus the legacy figure. Non-zero means '
             'the punches and the stored total disagree in the source.')
    merged_rows = fields.Integer(
        string='Merged Punches', readonly=True, default=1,
        help='How many legacy rows collapsed into this day. The source has '
             '2,780 duplicate employee/date pairs, mostly a real punch plus '
             'stray zero-duration device re-reads.')

    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('employee_date_uniq', 'unique(employee_id, date)',
         'This employee already has a derived day for that date.'),
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another day already carries this legacy ID.'),
    ]

    @api.depends('check_in', 'check_out')
    def _compute_single_punch(self):
        for record in self:
            record.single_punch = bool(record.check_in) != bool(record.check_out)

    @api.depends('check_in', 'check_out')
    def _compute_worked_hours(self):
        for record in self:
            if record.check_in and record.check_out:
                delta = record.check_out - record.check_in
                record.worked_hours = max(delta.total_seconds() / 3600.0, 0.0)
            else:
                record.worked_hours = 0.0

    @api.depends('scheduled_hours', 'worked_hours', 'state', 'single_punch')
    def _compute_shortfall(self):
        for record in self:
            # A single fingerprint is penalised separately (Finger), so no
            # unachieved hours on top of it.
            if record.state != 'present' or record.single_punch:
                record.shortfall_hours = 0.0
                continue
            record.shortfall_hours = max(
                record.scheduled_hours - record.worked_hours, 0.0)

    @api.depends('worked_hours', 'legacy_worked_hours')
    def _compute_variance(self):
        for record in self:
            record.worked_hours_variance = (
                record.worked_hours - record.legacy_worked_hours)

    @api.depends('state', 'is_paid_leave')
    def _compute_absence_days(self):
        for record in self:
            if record.state == 'absent':
                record.absence_days = 1.0
            elif record.state == 'leave' and not record.is_paid_leave:
                record.absence_days = 1.0
            else:
                record.absence_days = 0.0

    @api.model
    def totals_for_period(self, employee, date_from, date_to):
        """Aggregate a month for the payroll engine.

        Returns plain floats rather than recordsets so the payroll engine has
        one narrow, testable interface to this model.
        """
        days = self.search([
            ('employee_id', '=', employee.id),
            ('date', '>=', date_from),
            ('date', '<=', date_to),
        ])
        return {
            'absence_days': sum(days.mapped('absence_days')),
            'late_minutes': sum(days.mapped('late_minutes')),
            'early_leave_minutes': sum(days.mapped('early_leave_minutes')),
            'shortfall_hours': sum(days.mapped('shortfall_hours')),
            'overtime_hours': sum(days.mapped('overtime_hours')),
            'single_punch_count': len(days.filtered('single_punch')),
            'worked_hours': sum(days.mapped('worked_hours')),
            'day_count': len(days),
        }
