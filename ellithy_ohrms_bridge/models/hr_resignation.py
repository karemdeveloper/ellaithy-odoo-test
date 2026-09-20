from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

# CR 2.9 -- the agreed wording. The stock OpenHRMS pair is "Normal
# Resignation" / "Fired by the company", which reads as an accusation on a
# document the employee signs, and covers neither a contract that simply ends
# nor a mutually agreed exit.
# Redefining the selection rather than extending it: CR 2.9 relabels the two
# existing entries as well as adding three, and ``selection_add`` can only
# add. Odoo logs a warning for the full redefinition; it is deliberate.
RESIGNATION_TYPE = [
    ('resigned', 'Resignation'),
    ('mutual', 'Mutual Agreement'),
    ('contract_end', 'End of Contract'),
    ('retirement', 'Retirement'),
    ('fired', 'Termination by Company'),
]

# ``ellithy_hr_base`` carries its own exit vocabulary on ``hr.employee``,
# reproduced from the legacy platform, and a constraint that refuses to
# archive anyone who is not carrying both exit dates. Approving a resignation
# archives the employee, so the two vocabularies have to be kept in step or
# the approval simply fails.
#
#   OHRMS type   -> (employee.resignation_type, employee.inactive_type)
EXIT_TYPE_MAP = {
    'resigned': ('resignation', 'resignation'),
    'mutual': ('resignation', 'resignation'),
    'contract_end': ('contract_expiration', 'termination'),
    'retirement': ('termination_of_service', 'termination'),
    'fired': ('termination_of_service', 'termination'),
}


class HrResignation(models.Model):
    """Ellithy's resignation policy on the OpenHRMS resignation.

    * CR 2.7 -- one screen. The record is reached from the employee through a
      smart button rather than duplicated onto the employee form.
    * CR 2.8 -- an approval cycle: the employee confirms, the line manager
      endorses, HR approves.
    * CR 2.9 -- the agreed type wording.
    * CR 2.10 -- a clearance checklist, run after the exit is approved, on
      the employee's actual last working day.
    """

    _name = 'hr.resignation'
    _inherit = ['hr.resignation', 'ellithy.hr.action.notification']

    # ------------------------------------------------------------------
    # What kind of status change this is
    # ------------------------------------------------------------------
    # Suspension and blacklisting used to live in a separate wizard on the
    # employee form, which meant two screens could take someone off the
    # payroll and only one of them left a record you could open, review or
    # approve. Folding them in here keeps CR 2.7's "one screen" true for
    # every way an employee stops working, and gives a suspension the same
    # endorse/approve trail an exit gets.
    #
    # A suspension is NOT an exit: it is bounded by an end date, and the
    # employee comes back. The two share the approval cycle and the archive
    # mechanics, and part company at ``_apply_employee_exit``.
    request_type = fields.Selection(
        [('exit', 'Exit'), ('suspension', 'Suspension')],
        string='Request Type', default='exit', required=True, tracking=True)

    suspension_start = fields.Date(
        string='Suspension Start',
        help='First day the employee is suspended.')
    suspension_end = fields.Date(
        string='Suspension End',
        help='Last day of the suspension. The daily job reinstates the '
             'employee the day after this date. Leave empty for a suspension '
             'with no agreed end, which must then be lifted by hand.')
    suspension_reason_id = fields.Many2one(
        'ellithy.hr.suspension.reason', string='Suspension Reason',
        ondelete='restrict')
    suspension_comment = fields.Text(string='Suspension Comment')

    blacklist = fields.Boolean(
        string='Blacklist',
        help='Mark the employee as not eligible for rehire. Written onto '
             'their record when this request is approved.')
    blacklist_reason = fields.Text(
        string='Blacklist Reason',
        help='Required when blacklisting. It is the only justification the '
             "employee's file will carry.")
    disable_login = fields.Boolean(
        string='Disable Login', default=True,
        help='Deactivate the linked user when the employee is archived.')

    resignation_type = fields.Selection(
        selection=RESIGNATION_TYPE,
        help='How the employment ended. Drives the departure reason written '
             'onto the employee record.')

    # The vendor fills ``joined_date`` from an onchange, so a resignation
    # created any way other than by typing into the form arrives without one
    # -- and confirmation then refuses it with "Please set a Joining Date".
    # A stored compute gives the same default to the form, the ORM, an
    # import and the migration alike, and stays editable.
    joined_date = fields.Date(
        compute='_compute_joined_date', store=True, readonly=False,
        precompute=True)

    # The vendor makes ``expected_revealing_date`` required, which reads as
    # "last day of employment". For a suspension the equivalent is the day
    # they stop coming in, so it is filled from the suspension start rather
    # than asked for twice.
    # ``required=False`` is deliberate. The vendor marks it required, which
    # puts a NOT NULL on the column -- and that fires at INSERT, before any
    # constraint can run, so a suspension missing its start date died with a
    # raw psycopg2 error instead of a sentence anyone could act on. The rule
    # is now stated per request type in ``_check_request_shape``.
    expected_revealing_date = fields.Date(
        compute='_compute_expected_revealing_date', store=True,
        readonly=False, precompute=True, required=False)

    # The vendor makes this required unconditionally, which does not fit a
    # suspension: it already has its own ``suspension_reason_id`` /
    # ``suspension_comment``, so a generic "Resignation Details" reason
    # would be a second, differently-labelled place to say the same thing
    # -- and it is hidden from the form for a suspension besides (see the
    # view), which would leave a required field nobody could fill in.
    # Required only for an exit, alongside the other exit-only fields, in
    # ``_check_request_shape``.
    reason = fields.Text(required=False)

    # ------------------------------------------------------------------
    # Employee self-service: what HR decides, not the leaver
    # ------------------------------------------------------------------
    # A normal employee raises an exit, never a suspension, and cannot pick
    # how it is legally classified, blacklist themselves, or switch off
    # their own login -- those are HR's calls, made while confirming or
    # endorsing the request. The form hides these fields from anyone
    # outside HR (``groups="ellithy_ohrms_bridge.resignation_generalist"``), but hiding a field from
    # the form does not stop an RPC/import call from setting it, so the
    # same list is enforced here too.
    _HR_ONLY_FIELDS = {
        'request_type', 'resignation_type', 'blacklist', 'blacklist_reason',
        'disable_login', 'suspension_start', 'suspension_end',
        'suspension_reason_id', 'suspension_comment',
    }

    def unlink(self):
        if not self.env.su and any(record.state not in ('draft',) for record in self):
            raise ValidationError(_('Only draft documents can be deleted.'))
        return super().unlink()

    def _is_hr_reviewer(self):
        return self.env.su or self.env.user.has_group('ellithy_ohrms_bridge.resignation_generalist')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_request_employee(vals.get('employee_id', self.env.user.employee_id.id),
                                         'ellithy_ohrms_bridge.resignation_generalist')
        if not self._is_hr_reviewer():
            for vals in vals_list:
                blocked = self._HR_ONLY_FIELDS & vals.keys()
                if blocked:
                    raise AccessError(_(
                        'Only HR can set %(fields)s.',
                        fields=', '.join(sorted(blocked))))
                vals['request_type'] = 'exit'
                vals.setdefault('resignation_type', 'resigned')
        return super().create(vals_list)

    # ``employee_contract`` is the vendor's free-text copy of the contract's
    # name, kept as-is (retyping it in place fails outright: migrated rows
    # hold values Postgres cannot cast to an integer, e.g. the literal text
    # "New"). A real relation alongside it instead, which is also the one
    # shown on the form -- the plain text column is dropped from the view
    # entirely rather than merely hidden from the employee.
    # Stored and precomputed, like ``joined_date`` above, so it is filled in
    # on a plain ``create()`` too -- not just when the employee is picked
    # interactively and the onchange happens to run -- while staying
    # editable for HR afterward.
    employee_contract_id = fields.Many2one(
        'hr.contract', string='Contract', ondelete='set null',
        compute='_compute_employee_contract_id', store=True,
        readonly=False, precompute=True)

    @api.depends('employee_id')
    def _compute_employee_contract_id(self):
        for resignation in self:
            if not resignation.employee_contract_id:
                # The same "current contract" lookup payroll and loan
                # eligibility already use: the one covering today, or --
                # for someone whose contract was never dated to cover the
                # present, which is exactly the shape a resignation deals
                # with -- their last one.
                resignation.employee_contract_id = (
                    resignation.employee_id._ibs_contract_on(
                        fields.Date.context_today(resignation)))

    def write(self, vals):
        if 'employee_id' in vals:
            self._check_request_employee(vals['employee_id'],
                                         'ellithy_ohrms_bridge.resignation_generalist')
        target = vals.get('state')
        if not self.env.su and target in ('endorsed', 'approved'):
            role = 'resignation_admin' if target == 'approved' else 'resignation_generalist'
            if not self.env.user.has_group('ellithy_ohrms_bridge.' + role):
                raise AccessError(_('You are not authorized for this resignation approval.'))
            expected = 'endorsed' if target == 'approved' else 'confirm'
            if any(record.state != expected for record in self):
                raise ValidationError(_('Follow the resignation approval order.'))
            if any(record.employee_id.user_id == self.env.user for record in self):
                raise ValidationError(_('You cannot approve your own resignation.'))
        if not self._is_hr_reviewer():
            blocked = self._HR_ONLY_FIELDS & vals.keys()
            if blocked:
                raise AccessError(_(
                    'Only HR can change %(fields)s.',
                    fields=', '.join(sorted(blocked))))
        result = super().write(vals)
        if target == 'confirm':
            self._notify_approval_group('ellithy_ohrms_bridge.resignation_generalist', _('Resignation awaiting HR endorsement'))
        elif target == 'endorsed':
            self._notify_approval_group('ellithy_ohrms_bridge.resignation_admin', _('Resignation awaiting HR Admin approval'))
        elif target in ('approved', 'cancel', 'rejected'):
            self._notify_employee(_('Resignation updated'))
        if vals.get('clearance_state') == 'progress':
            self._notify_approval_group('ellithy_ohrms_bridge.resignation_generalist',
                                       _('Clearance awaiting department reviews'))
        elif vals.get('clearance_state') == 'done':
            self._notify_employee(_('Clearance completed'))
        return result

    @api.depends('request_type', 'suspension_start')
    def _compute_expected_revealing_date(self):
        for resignation in self:
            if (resignation.request_type == 'suspension'
                    and resignation.suspension_start):
                resignation.expected_revealing_date = (
                    resignation.suspension_start)
            elif not resignation.expected_revealing_date:
                resignation.expected_revealing_date = False

    @api.constrains('request_type', 'suspension_start', 'suspension_end',
                    'resignation_type', 'expected_revealing_date', 'reason')
    def _check_request_shape(self):
        for resignation in self:
            if resignation.request_type == 'suspension':
                if not resignation.suspension_start:
                    raise ValidationError(
                        _('A suspension needs a start date.'))
                if (resignation.suspension_end
                        and resignation.suspension_end
                        < resignation.suspension_start):
                    raise ValidationError(_(
                        'The suspension cannot end before it starts.'))
                continue
            if not resignation.expected_revealing_date:
                raise ValidationError(
                    _('An exit needs a last day of employment.'))
            if not resignation.reason:
                raise ValidationError(_('An exit needs a reason.'))
            if not resignation.resignation_type:
                # Only enforced once the request leaves draft: the type is
                # chosen during review, not necessarily when raising it.
                if resignation.state != 'draft':
                    raise ValidationError(
                        _('An exit needs a resignation type.'))

    @api.constrains('blacklist', 'blacklist_reason')
    def _check_blacklist_reason(self):
        for resignation in self:
            if resignation.blacklist and not resignation.blacklist_reason:
                raise ValidationError(
                    _('Blacklisting an employee requires a reason.'))

    # ``hr_resignation`` refuses a new request whenever the employee has ANY
    # confirmed or approved one -- without excluding the record being
    # checked, so creating one directly as approved refuses itself. With 605
    # historical exits now migrated, it also made every ex-employee
    # unselectable, and it would have blocked an exit for anyone previously
    # suspended. Narrowed to what it was defending against: one status
    # change at a time.
    def _conflicting_requests(self):
        self.ensure_one()
        if not self.employee_id:
            return self.browse()
        return self.search([
            ('id', '!=', self.id or False),
            ('employee_id', '=', self.employee_id.id),
            '|',
                ('state', 'in', ('confirm', 'endorsed')),
                '&', ('state', '=', 'approved'), ('request_type', '=', 'exit'),
        ])

    @api.constrains('joined_date')
    def _check_joined_date(self):
        for resignation in self:
            if resignation._conflicting_requests():
                raise ValidationError(_(
                    'There is already a status change in progress for '
                    '%(name)s.', name=resignation.employee_id.name))

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        """Same narrowing as the constraint above.

        The stock onchange raises the moment you pick an employee who has any
        historical resignation, which after the migration is most ex-staff.
        """
        self.joined_date = self.employee_id.joining_date
        # ``employee_contract_id`` is handled by its own compute above,
        # which runs here too since it depends on ``employee_id``. Only the
        # vendor's legacy text copy and the notice period still need
        # setting explicitly.
        contract = self.employee_contract_id
        if contract:
            self.employee_contract = contract.name
            self.notice_period = contract.notice_days

    @api.depends('employee_id')
    def _compute_joined_date(self):
        for resignation in self:
            if not resignation.joined_date:
                resignation.joined_date = (
                    resignation.employee_id.joining_date)

    # ---- CR 2.8: an endorsement step between confirm and approve ---------
    state = fields.Selection(
        selection_add=[('endorsed', 'Endorsed by Manager'), ('approved',)],
        ondelete={'endorsed': 'set default'})
    endorsed_by = fields.Many2one(
        'res.users', string='Endorsed By', readonly=True, copy=False)
    endorsed_at = fields.Datetime(
        string='Endorsed On', readonly=True, copy=False)
    approved_by = fields.Many2one(
        'res.users', string='Approved By', readonly=True, copy=False)
    approved_at = fields.Datetime(
        string='Approved On', readonly=True, copy=False)
    rejection_reason = fields.Text(
        string='Rejection Reason', copy=False,
        help='Required to reject a resignation.')

    # ---- CR 2.10: clearance ---------------------------------------------
    # Clearance is started deliberately, from a wizard that confirms the last
    # working day and picks the departments the leaver has to visit. It is
    # not laid out automatically on confirmation, because which departments
    # owe a sign-off depends on the leaver -- a driver clears Fleet, a
    # cashier clears Treasury -- and a checklist nobody chose is a checklist
    # nobody reads.
    clearance_state = fields.Selection(
        [('none', 'Not Started'),
         ('progress', 'In Progress'),
         ('done', 'Cleared')],
        string='Clearance', default='none', required=True, tracking=True,
        copy=False)
    clearance_line_ids = fields.One2many(
        'hr.resignation.clearance', 'resignation_id', string='Clearance',
        copy=False)
    clearance_confirmed_by = fields.Many2one(
        'res.users', string='Clearance Confirmed By', readonly=True,
        copy=False)
    clearance_confirmed_at = fields.Datetime(
        string='Clearance Confirmed On', readonly=True, copy=False)
    clearance_total_due = fields.Monetary(
        string='Total Due on Clearance', compute='_compute_clearance_totals',
        currency_field='currency_id',
        help='Sum of what the departments say is still outstanding. Carried '
             'into the final settlement.')
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', string='Currency')

    # Stored, because approval is gated on it and the gate has to be
    # searchable; the progress label beside it is display only. They are
    # computed separately -- Odoo requires one compute method per storage
    # class -- rather than sharing one.
    clearance_complete = fields.Boolean(
        string='All Departments Cleared',
        compute='_compute_clearance_complete', store=True)
    clearance_progress = fields.Char(
        string='Clearance Progress', compute='_compute_clearance_progress')

    @api.depends('clearance_line_ids.state')
    def _compute_clearance_complete(self):
        for resignation in self:
            lines = resignation.clearance_line_ids
            resignation.clearance_complete = bool(lines) and all(
                state == 'approved' for state in lines.mapped('state'))

    @api.depends('clearance_line_ids.state')
    def _compute_clearance_progress(self):
        for resignation in self:
            lines = resignation.clearance_line_ids
            cleared = lines.filtered(lambda l: l.state == 'approved')
            resignation.clearance_progress = '%s / %s' % (
                len(cleared), len(lines))

    @api.depends('clearance_line_ids.amount_due')
    def _compute_clearance_totals(self):
        for resignation in self:
            resignation.clearance_total_due = sum(
                resignation.clearance_line_ids.mapped('amount_due'))

    def action_open_clearance_wizard(self):
        """Start clearance: confirm the last day, pick the departments.

        Clearance now runs after the exit is approved, on the employee's
        actual last working day -- handing back company property is
        something that happens when they leave, not a precondition for
        deciding they may. The wizard itself re-checks the date (a stale
        open form should not let it through late), this is the button's own
        gate.
        """
        self.ensure_one()
        if self.request_type != 'exit':
            raise ValidationError(
                _('Clearance applies to an exit, not to a suspension.'))
        if self.state != 'approved':
            raise ValidationError(
                _('Clearance starts once the exit is approved.'))
        # Only the first opening of this wizard is "starting" clearance;
        # reopening it afterward to add one more department should not
        # start refusing once the day has moved on.
        if (self.clearance_state == 'none'
                and self.expected_revealing_date != fields.Date.context_today(self)):
            raise ValidationError(
                _('Clearance starts on the last working day '
                  '(%(day)s), not before.',
                  day=self.expected_revealing_date))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Start Clearance'),
            'res_model': 'hr.resignation.clearance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_resignation_id': self.id},
        }

    def action_confirm_clearance(self):
        """The final signature, once every department has signed.

        Kept separate from the departments' own sign-offs: the last one to
        clear should not silently close the form on everyone else's behalf,
        and HR needs a moment to read the outstanding amounts before
        clearance itself is marked done.
        """
        for resignation in self:
            if resignation.clearance_state != 'progress':
                raise ValidationError(
                    _('Clearance has not been started.'))
            blocked = resignation.clearance_line_ids.filtered(
                lambda line: line.state == 'rejected')
            if blocked:
                raise ValidationError(_(
                    'Clearance is blocked by %(departments)s.',
                    departments=', '.join(
                        blocked.mapped('department_id.display_name'))))
            if not resignation.clearance_complete:
                raise ValidationError(_(
                    'Clearance is not complete (%(progress)s). Every '
                    'department must sign before it can be confirmed.',
                    progress=resignation.clearance_progress))
            resignation.write({
                'clearance_state': 'done',
                'clearance_confirmed_by': self.env.user.id,
                'clearance_confirmed_at': fields.Datetime.now(),
            })

    def action_reopen_clearance(self):
        """Send a confirmed clearance back, when something was missed.

        No precondition on the resignation's own state: clearance now only
        ever exists once an exit is already approved, so requiring that
        here (as an earlier version of this method did, from when
        clearance ran before approval) would block reopening outright,
        always.
        """
        for resignation in self:
            resignation.write({
                'clearance_state': 'progress',
                'clearance_confirmed_by': False,
                'clearance_confirmed_at': False,
            })

    def action_view_clearance(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clearance - %(name)s', name=self.employee_id.name),
            'res_model': 'hr.resignation.clearance',
            'view_mode': 'list,form',
            'domain': [('resignation_id', '=', self.id)],
            'context': {'default_resignation_id': self.id},
        }

    # ------------------------------------------------------------------
    # CR 2.8 -- the approval cycle
    # ------------------------------------------------------------------
    def action_confirm_resignation(self):
        return super().action_confirm_resignation()

    def action_cancel_resignation(self):
        """The employee's own withdrawal -- only theirs to make, and only
        before anyone else has acted on it.

        The vendor method sets ``state = 'cancel'`` unconditionally, with no
        regard to how far the request has already moved. Once a manager has
        endorsed it (or further), withdrawing is no longer a unilateral
        thing the leaver can do by themselves.
        """
        for resignation in self:
            if resignation.state not in ('draft', 'confirm'):
                raise ValidationError(_(
                    'This request has already moved past confirmation and '
                    'can no longer be withdrawn. Ask HR to reject it '
                    'instead.'))
        return super().action_cancel_resignation()

    def action_endorse_resignation(self):
        """The line manager's endorsement, between confirm and HR approval."""
        if not self._is_hr_reviewer():
            raise AccessError(_('Only HR can endorse a resignation.'))
        for resignation in self:
            if resignation.state != 'confirm':
                raise ValidationError(_(
                    'Only a confirmed resignation can be endorsed.'))
            resignation.write({
                'state': 'endorsed',
                'endorsed_by': self.env.user.id,
                'endorsed_at': fields.Datetime.now(),
            })

    # ------------------------------------------------------------------
    # Leaving the company
    # ------------------------------------------------------------------
    # The stock approval archives the employee with a bare
    # ``employee_id.active = False``, then fills in the departure details
    # afterwards. That order cannot work here: ``ellithy_hr_base`` reproduces
    # a legacy database trigger which refuses to archive anyone who is not
    # already carrying both exit dates, and equally refuses to let an ACTIVE
    # employee hold them. Neither half of the stock sequence is a legal
    # intermediate state, so approving a resignation whose last day has
    # arrived fails outright with "Cannot archive X without both a
    # resignation date and a last working day".
    #
    # The exit is therefore applied as a single write, which is the only
    # state transition the constraint accepts.
    DEPARTURE_REASON_XMLID = {
        'resigned': 'hr.departure_resigned',
        'mutual': 'hr.departure_resigned',
        'contract_end': 'hr.departure_fired',
        'retirement': 'hr.departure_retired',
        'fired': 'hr.departure_fired',
    }

    def _departure_reason(self):
        """The stock departure reason matching the resignation type."""
        self.ensure_one()
        xmlid = self.DEPARTURE_REASON_XMLID.get(self.resignation_type)
        reason = self.env.ref(xmlid, raise_if_not_found=False) if xmlid else None
        if reason:
            return reason
        # Older databases carry these by name rather than by xmlid.
        name = 'Fired' if self.resignation_type in (
            'fired', 'contract_end') else 'Resigned'
        return self.env['hr.departure.reason'].search(
            [('name', '=', name)], limit=1)

    def _apply_employee_exit(self):
        """Take the employee off the payroll, once the day has come.

        A no-op while the start date is still in the future -- that is the
        daily job's business, below -- and for anyone already archived, so it
        is safe to call more than once.

        An exit and a suspension archive the employee the same way and
        differ only in what is written alongside: an exit records a
        departure, a suspension records a suspension and nothing about
        leaving.
        """
        today = fields.Date.context_today(self)
        for resignation in self:
            employee = resignation.employee_id
            if not employee or not employee.active:
                continue
            if resignation.request_type == 'suspension':
                start = resignation.suspension_start
                if not start or start > today:
                    continue
                # The legacy constraint wants both exit dates on any archived
                # employee, suspension included, so the suspension's own dates
                # stand in. ``inactive_type`` is what tells the two apart.
                values = {
                    'inactive_type': 'suspension',
                    'resignation_type': False,
                    'resignation_date': start,
                    'last_working_day': resignation.suspension_end or start,
                    'suspension_start': start,
                    'suspension_end': resignation.suspension_end,
                    'suspension_reason_id': (
                        resignation.suspension_reason_id.id),
                    'suspension_comment': (
                        resignation.suspension_comment or resignation.reason),
                }
            else:
                last_day = (resignation.approved_revealing_date
                            or resignation.expected_revealing_date)
                if not last_day or last_day > today:
                    continue
                resignation_type, inactive_type = EXIT_TYPE_MAP.get(
                    resignation.resignation_type, (False, False))
                values = {
                    # ellithy_hr_base's exit block
                    'resignation_type': resignation_type,
                    'inactive_type': inactive_type,
                    # The legacy pair is "when they resigned" and "their last
                    # day". A missing confirmation date is not a reason to
                    # block an approved exit, so the last day stands in.
                    'resignation_date': (
                        resignation.resign_confirm_date or last_day),
                    'last_working_day': last_day,
                    # hr_resignation's own block
                    'resign_date': last_day,
                    'resigned': resignation.resignation_type != 'fired',
                    'fired': resignation.resignation_type == 'fired',
                    # stock hr
                    'departure_reason_id': (
                        resignation._departure_reason().id),
                    'departure_date': last_day,
                    'departure_description': resignation.reason,
                }
            if resignation.blacklist:
                values.update({
                    'blacklist': True,
                    'blacklist_reason': resignation.blacklist_reason,
                })
            # One write: the constraint rejects both halves of the stock
            # sequence as intermediate states.
            employee.write(dict(values, active=False))
            employee.contract_ids.filtered(
                lambda c: c.state == 'open').write({'state': 'close'})
            if resignation.disable_login and employee.user_id:
                employee.user_id.active = False
                if resignation.request_type == 'exit':
                    # A suspended employee keeps their user link so the same
                    # login comes back when they do.
                    employee.user_id = False

    def _reinstate_employee(self):
        """Bring a suspended employee back once the suspension has run out.

        The exit fields have to go in the same write that reactivates them:
        the legacy constraint refuses to let an active employee hold either.
        """
        today = fields.Date.context_today(self)
        for resignation in self:
            employee = resignation.employee_id
            if resignation.request_type != 'suspension' or not employee:
                continue
            if employee.active or not resignation.suspension_end:
                continue
            if resignation.suspension_end >= today:
                continue
            employee.write({
                'active': True,
                'inactive_type': False,
                'resignation_type': False,
                'resignation_date': False,
                'last_working_day': False,
            })
            if employee.user_id:
                employee.user_id.active = True
            employee.message_post(body=_(
                'Suspension ended on %(day)s. Employee reinstated.',
                day=resignation.suspension_end))

    def action_approve_resignation(self):
        """HR's approval, and the last of the three.

        One gate the stock method does not have: the manager must have
        endorsed. Checked before delegating, because the stock method
        deactivates the employee and closes the contract -- by the time it
        has run there is nothing left to refuse.

        Clearance is not a precondition here: it is handing company
        property back on the leaver's actual last day, which comes after
        the decision to approve the exit, not before it. It can only be
        started once this method has run (see
        ``action_open_clearance_wizard``).
        """
        if not (self.env.su or self.env.user.has_group('ellithy_ohrms_bridge.resignation_admin')):
            raise AccessError(_('Only HR management can approve a resignation.'))
        for resignation in self:
            if resignation.state != 'endorsed':
                raise ValidationError(_(
                    'A resignation is approved after the line manager has '
                    'endorsed it. This one is still %(state)s.',
                    state=dict(
                        self._fields['state']._description_selection(self.env)
                    ).get(resignation.state, resignation.state)))
        # Archive first, so the stock method's own archive block -- the half
        # that cannot satisfy the constraint -- is skipped as already done,
        # while everything else it does still runs.
        self._apply_employee_exit()
        exits = self.filtered(lambda r: r.request_type == 'exit')
        if exits:
            super(HrResignation, exits).action_approve_resignation()
            # The stock method only flips ``state`` to 'approved' inside its
            # own "contract is still open" branch -- but ``_apply_employee_exit``
            # above has *just* closed that same contract for any exit whose
            # last day has already arrived, which is silently the common
            # case (approving something that is due now or overdue). Left
            # alone, that leaves the record stuck on 'endorsed' forever:
            # the click "succeeds" with no error, and nothing visibly
            # happens. Every gate above has already passed, so it is
            # approved regardless of what the stock method's own contract
            # lookup happened to find.
            exits.filtered(lambda r: r.state != 'approved').write({
                'state': 'approved'})
        # The stock method cancels the contract and stamps a departure
        # reason, neither of which belongs on a suspension: the employee is
        # coming back to the same contract.
        suspensions = self - exits
        suspensions.write({
            'state': 'approved',
            'approved_revealing_date': False,
        })
        self.write({
            'approved_by': self.env.user.id,
            'approved_at': fields.Datetime.now(),
        })
        return True

    @api.model
    def update_employee_status(self):
        """Archive leavers whose last working day has arrived.

        ``hr_resignation`` ships a daily cron calling this method, but never
        defines it -- so the job has been failing with an AttributeError on
        every run, and an approved resignation dated in the future was never
        acted upon. Defining it here is what makes approving a resignation
        ahead of time actually mean something, and it is also what ends a
        suspension on its last day without anyone remembering to.
        """
        approved = self.search([('state', '=', 'approved')])
        approved.filtered(
            lambda r: r.employee_id.active)._apply_employee_exit()
        # And the other direction: a suspension that has run its course.
        approved.filtered(
            lambda r: r.request_type == 'suspension'
        )._reinstate_employee()
        return True

    def action_reject_resignation(self):
        for resignation in self:
            if not resignation.rejection_reason:
                raise ValidationError(
                    _('Rejecting a resignation requires a reason.'))
        return super().action_reject_resignation()

    def action_reset_to_draft(self):
        """Reopen a resignation, and undo what approving it wrote.

        Same constraint, mirrored: an active employee may not hold exit
        dates, so reactivating and clearing them is one write rather than
        two. The stock method's own ``active = True`` then finds nothing
        left to do.
        """
        self.employee_id.write({
            'active': True,
            'resignation_type': False,
            'inactive_type': False,
            'resignation_date': False,
            'last_working_day': False,
            'departure_reason_id': False,
            'departure_date': False,
            'suspension_start': False,
            'suspension_end': False,
            'suspension_reason_id': False,
            'suspension_comment': False,
        })
        result = super().action_reset_to_draft()
        self.write({
            'endorsed_by': False, 'endorsed_at': False,
            'approved_by': False, 'approved_at': False,
        })
        return result


class HrResignationClearance(models.Model):
    """One department's sign-off on one leaver.

    A clearance form is a sheet that goes round the departments a leaver owes
    something to -- IT wants the laptop, Finance wants the advance settled,
    Stores wants the uniform -- and comes back signed. The model is that
    sheet: one row per department, each carrying its own signature and the
    moment it was given, so "who cleared him and when" has an answer months
    later.

    Rows are raised by the clearance wizard rather than configured in
    advance, because which departments a given leaver has to visit depends on
    the leaver.
    """

    _name = 'hr.resignation.clearance'
    _description = 'Clearance Line'
    _order = 'sequence, id'
    _rec_name = 'department_id'

    resignation_id = fields.Many2one(
        'hr.resignation', string='Resignation', required=True, index=True,
        ondelete='cascade')
    department_id = fields.Many2one(
        'hr.department', string='Department', required=True,
        ondelete='restrict')
    manager_id = fields.Many2one(
        related='department_id.manager_id', string='Department Manager',
        store=True)
    sequence = fields.Integer(default=10)
    employee_id = fields.Many2one(
        related='resignation_id.employee_id', store=True, string='Employee')

    state = fields.Selection(
        [('pending', 'Pending'),
         ('approved', 'Cleared'),
         ('rejected', 'Blocked')],
        string='Status', default='pending', required=True)
    approved_by = fields.Many2one(
        'res.users', string='Signed By', readonly=True, copy=False)
    approved_at = fields.Datetime(
        string='Signed On', readonly=True, copy=False)
    rejection_reason = fields.Text(
        string='Reason', copy=False,
        help='Required to block clearance: what the leaver still owes this '
             'department.')

    amount_due = fields.Monetary(
        string='Amount Due', currency_field='currency_id',
        help='Anything the leaver still owes this department, carried into '
             'the final settlement.')
    currency_id = fields.Many2one(
        related='resignation_id.employee_id.company_id.currency_id',
        store=True)
    note = fields.Text()

    _sql_constraints = [
        ('resignation_department_uniq',
         'unique(resignation_id, department_id)',
         'This department is already on the clearance form.'),
    ]

    def _check_approver(self):
        """Who may sign a department's line.

        The department's own manager, or HR. Anyone else signing on a
        department's behalf defeats the point of recording who signed.
        """
        if self.env.su:
            return
        user = self.env.user
        if user.has_group('ellithy_ohrms_bridge.resignation_admin'):
            return
        for line in self:
            if line.department_id.manager_id.user_id == user:
                continue
            raise ValidationError(_(
                'Clearance for %(department)s is signed by its manager or by '
                'HR.', department=line.department_id.display_name))

    # Only the signature itself is gated -- HR Personnel keep the plain ACL
    # write they already have for the amount/note columns; it is setting
    # the outcome that is reserved for HR management or the department's
    # own manager.
    _SIGNATURE_FIELDS = {'state', 'approved_by', 'approved_at'}

    def write(self, vals):
        # The action methods below already call ``_check_approver``; this
        # closes the same gate against a direct write (RPC/import) that
        # skips them entirely -- an employee is not the ACL, and the ACL
        # alone lets any employee write to any clearance line.
        if self._SIGNATURE_FIELDS & vals.keys():
            self._check_approver()
        return super().write(vals)

    def action_approve(self):
        self._check_approver()
        for line in self:
            if line.state == 'approved':
                continue
            line.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
                'rejection_reason': False,
            })
            line.resignation_id.message_post(body=_(
                '%(department)s cleared by %(user)s.',
                department=line.department_id.display_name,
                user=self.env.user.display_name))

    def action_reject(self):
        """Block clearance, with what is outstanding."""
        self._check_approver()
        for line in self:
            if not line.rejection_reason:
                raise ValidationError(_(
                    'Blocking clearance for %(department)s requires a '
                    'reason.', department=line.department_id.display_name))
            line.write({
                'state': 'rejected',
                'approved_by': self.env.user.id,
                'approved_at': fields.Datetime.now(),
            })
            line.resignation_id.message_post(body=_(
                '%(department)s blocked clearance: %(reason)s',
                department=line.department_id.display_name,
                reason=line.rejection_reason))

    def action_reset(self):
        self._check_approver()
        self.write({'state': 'pending', 'approved_by': False,
                    'approved_at': False})
