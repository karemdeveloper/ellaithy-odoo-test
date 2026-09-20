import hashlib

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

VACATION_ROLE = [
    ('15', '15 Days'),
    ('21', '21 Days'),
    ('30', '30 Days'),
]

TIME_ROLE = [
    ('fixed', 'Fixed'),
    ('flexible', 'Flexible'),
]

WORK_TYPE = [
    ('full_time', 'Full Time'),
    ('part_time', 'Part Time'),
    ('remotely', 'Remotely'),
]

WORKSPACE_TYPE = [
    ('office', 'Office'),
    ('home', 'Home'),
]

OVERTIME_ROLE = [
    ('none', 'None'),
    ('all', 'All Overtime'),
    ('4hr', 'Overtime 4hr'),
    ('2hr', 'Overtime 2hr'),
    ('fri_sat', 'Overtime Fri & Sat'),
]

OVERTIME_REPORT = [
    ('system', 'System'),
    ('report', 'Report'),
]

RELIGION = [
    ('muslim', 'Muslim'),
    ('christian', 'Christian'),
]

INACTIVE_TYPE = [
    ('termination', 'Termination'),
    ('resignation', 'Resignation'),
    ('suspension', 'Suspension'),
]

RESIGNATION_TYPE = [
    ('resignation', 'Resignation'),
    ('termination_of_service', 'Termination of Service'),
    ('contract_expiration', 'Contract Expiration'),
]


class HrEmployee(models.Model):
    """Employee master.

    Extends ``hr.employee`` to cover the legacy ``users`` table (156 columns).
    Roughly a third of those columns map onto stock Odoo fields; the rest are
    added here, and three repeated column groups -- dependants, HR documents
    and payout accounts -- are normalised into child models instead of being
    carried as flat repeated columns.

    Salary and insurance amounts deliberately live on ``hr.contract`` rather
    than here, so a raise does not overwrite history.
    """

    _inherit = 'hr.employee'

    # Every Many2one to an employee resolves through name_search, so listing
    # the code here makes "EMP-1441" find the person in any assignment field
    # -- department head, manager, coach, warning, payslip -- without touching
    # each view. Arabic name is included because half the directory is
    # recorded that way.
    _rec_names_search = ['name', 'employee_code', 'name_ar', 'work_email']

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name_ar = fields.Char(string='Arabic Name', index='trigram')
    employee_code = fields.Char(
        string='Employee Code', copy=False, index=True, readonly=True,
        default=lambda self: _('New'))
    card_issue_date = fields.Date(string='ID Card Issue Date')
    religion = fields.Selection(RELIGION, string='Religion')
    office_number = fields.Char(string='Office Number')
    profession = fields.Char(string='Profession')
    created_from = fields.Char(
        string='Created From',
        help='Free-text origin marker carried over from the legacy system.')

    # ------------------------------------------------------------------
    # Org placement
    # ------------------------------------------------------------------
    branch_id = fields.Many2one(
        'ellithy.branch', string='Branch', index=True, ondelete='restrict',
        tracking=True,
        help='An employee\'s branch is independent of their department\'s '
             'branch -- the legacy data has one department spread across '
             'several branches.')
    section_id = fields.Many2one(
        'hr.department', string='Section', index=True, ondelete='restrict',
        domain="[('dept_type', '=', 'section')]", tracking=True)
    grade_id = fields.Many2one(
        'ellithy.hr.grade', string='Grade', index=True, ondelete='restrict',
        tracking=True)

    # ------------------------------------------------------------------
    # Employment terms
    # ------------------------------------------------------------------
    joining_date = fields.Date(string='Joining Date', tracking=True)
    vacation_role = fields.Selection(
        VACATION_ROLE, string='Vacation Role', default='15',
        help='Legacy vacation tier: 15 denotes 8 annual and 7 separate casual '
             'days in the first year. The computed Annual Leave Entitlement '
             'shows annual days only: 8 initially, 14 after a year and 30 '
             'with ten years of insured service.')
    time_role = fields.Selection(TIME_ROLE, string='Time Role')
    work_type = fields.Selection(WORK_TYPE, string='Work Type')
    workspace_type = fields.Selection(WORKSPACE_TYPE, string='Workplace')
    overtime_role = fields.Selection(
        OVERTIME_ROLE, string='Overtime Role',
        help='Overtime entitlement policy, not a rate.')
    overtime_report = fields.Selection(
        OVERTIME_REPORT, string='Overtime Source',
        help='Whether overtime is derived from attendance or submitted '
             'manually.')
    evaluation_date = fields.Date(string='Evaluation Date')
    evaluation_mail_sent_at = fields.Datetime(
        string='Evaluation Mail Sent', readonly=True)

    # ------------------------------------------------------------------
    # Insurance -- entered on the contract, shown here
    # ------------------------------------------------------------------
    # Both insurances are terms of an engagement: the tier, the costs, the
    # subscription salary a contribution is calculated on and the office an
    # employee is registered at all belong to the contract that agreed them.
    # Held on the employee, renewing a contract silently rewrote the figures
    # the previous one was filed under.
    #
    # They are mirrored here so the employee file still answers "what is
    # this person insured for" in one place, and so reports and the leave
    # entitlement rule keep reading them from the employee.
    #
    # Writable on purpose, though the form shows them read-only. A related
    # field left at its default ``readonly=True`` does not reject a write --
    # it drops it silently, so an import or a script aimed at the employee
    # would lose the values without a word. Writable, the same write lands on
    # the contract, which is where it belonged.
    medical_insurance_date = fields.Date(
        related='contract_id.medical_insurance_date', readonly=False,
        string='Medical Insurance Date')
    medical_insurance_type = fields.Selection(
        related='contract_id.medical_insurance_type', readonly=False,
        string='Medical Insurance Type')
    medical_card_number = fields.Char(
        related='contract_id.medical_card_number', readonly=False,
        string='Medical Card Number')
    medical_cost_per_year = fields.Monetary(
        related='contract_id.medical_cost_per_year', readonly=False, string='Cost Per Year',
        currency_field='currency_id')
    medical_cost_per_month = fields.Monetary(
        related='contract_id.medical_cost_per_month', readonly=False, string='Cost Per Month',
        currency_field='currency_id')
    medical_employee_share = fields.Float(
        related='contract_id.medical_employee_share', readonly=False,
        string='Employee Share (%)')
    has_medical_relative = fields.Boolean(
        related='contract_id.has_medical_relative', readonly=False,
        string='Has Covered Relatives')

    # A dependant belongs to the person, not to the engagement, so the list
    # itself stays on the employee.
    dependant_ids = fields.One2many(
        'ellithy.hr.dependant', 'employee_id', string='Covered Relatives')
    dependant_count = fields.Integer(
        string='Relatives', compute='_compute_dependant_count')

    # ------------------------------------------------------------------
    # Social insurance -- entered on the contract, shown here
    #
    # Field order follows the legacy form: enrolment flag, office, number,
    # start date, then the three salary figures and the profession. The
    # salary figures stay writable, because HR has always set a raise from
    # the employee file and that edit lands on the running contract.
    # ------------------------------------------------------------------
    has_social_insurance = fields.Boolean(
        related='contract_id.has_social_insurance', readonly=False,
        string='Has Social Insurance')
    social_insurance_office_id = fields.Many2one(
        related='contract_id.social_insurance_office_id', readonly=False,
        string='Social Insurance Office')
    social_insurance_number = fields.Char(
        related='contract_id.social_insurance_number', readonly=False,
        string='Social Insurance Number')
    social_insurance_start_date = fields.Date(
        related='contract_id.social_insurance_start_date', readonly=False,
        string='Social Insurance Start Date')

    basic_salary = fields.Monetary(
        related='contract_id.wage', string='Basic Salary',
        readonly=False, currency_field='currency_id')
    subscription_salary = fields.Monetary(
        related='contract_id.subscription_wage', string='Subscription Salary',
        readonly=False, currency_field='currency_id')
    total_salary = fields.Monetary(
        related='contract_id.total_wage', string='Total Salary',
        readonly=False, currency_field='currency_id')

    # ---- superseded insurance columns, kept for reference --------------
    insurance_number = fields.Char(
        related='contract_id.insurance_number', readonly=False,
        string='Insurance Number (legacy)')
    insurance_office = fields.Char(
        related='contract_id.insurance_office', readonly=False,
        string='Insurance Office (legacy)')
    insurance_entered_date = fields.Date(
        related='contract_id.insurance_entered_date', readonly=False,
        string='Insurance Registration Date')
    insurance_salary = fields.Monetary(
        related='contract_id.insurance_salary', readonly=False, string='Insured Salary',
        currency_field='currency_id')
    social_insurance_price = fields.Monetary(
        related='contract_id.social_insurance_price', readonly=False,
        string='Social Insurance Cost', currency_field='currency_id')

    # ------------------------------------------------------------------
    # Entitlement flags
    # ------------------------------------------------------------------
    has_uniform = fields.Boolean(
        string='Uniform',
        help='Entitled to a uniform. The items actually issued are listed '
             'separately below.')
    uniform_ids = fields.Many2many(
        'ellithy.hr.uniform', 'ellithy_hr_uniform_employee_rel',
        'employee_id', 'uniform_id', string='Uniforms Issued')
    has_id_file = fields.Boolean(string='ID File')
    has_mobile = fields.Boolean(string='Mobile')
    has_medical = fields.Boolean(string='Medical')
    has_addition = fields.Boolean(string='Addition')
    # These four exist in the legacy schema but carry no data: across 1,226
    # live employees, mob_price, medical_price and detection are zero on every
    # row and personal_card is set on three. They are kept so the columns are
    # not lost, but hidden behind developer mode rather than shown on a form
    # where they would only ever read 0.00.
    mobile_price = fields.Monetary(
        string='Mobile Cost', currency_field='currency_id')
    medical_price = fields.Monetary(
        string='Medical Cost', currency_field='currency_id')
    detection_price = fields.Monetary(
        string='Checkup Cost', currency_field='currency_id')
    personal_card_price = fields.Monetary(
        string='Personal Card Cost', currency_field='currency_id')

    # ------------------------------------------------------------------
    # HR document file
    # ------------------------------------------------------------------
    document_ids = fields.One2many(
        'ellithy.hr.document', 'employee_id', string='HR Documents')
    document_completeness = fields.Float(
        string='File Completeness (%)', compute='_compute_document_completeness',
        store=True, digits=(5, 2),
        help='Share of required document types that have been received.')

    # ------------------------------------------------------------------
    # Payout accounts
    # ------------------------------------------------------------------
    payout_account_ids = fields.One2many(
        'ellithy.hr.account', 'employee_id', string='Payout Accounts')

    # ------------------------------------------------------------------
    # Exit and status
    # ------------------------------------------------------------------
    inactive_type = fields.Selection(
        INACTIVE_TYPE, string='Inactive Type', tracking=True, copy=False)
    resignation_type = fields.Selection(
        RESIGNATION_TYPE, string='Resignation Type', tracking=True, copy=False)
    resignation_date = fields.Date(
        string='Resignation Date', tracking=True, copy=False)
    last_working_day = fields.Date(
        string='Last Working Day', tracking=True, copy=False)
    blacklist = fields.Boolean(string='Blacklisted', tracking=True, copy=False)
    blacklist_reason = fields.Text(string='Blacklist Reason', copy=False)
    suspension_start = fields.Date(string='Suspension Start', copy=False)
    suspension_end = fields.Date(string='Suspension End', copy=False)
    suspension_reason_id = fields.Many2one(
        'ellithy.hr.suspension.reason', string='Suspension Reason',
        ondelete='restrict', copy=False)
    suspension_comment = fields.Text(string='Suspension Comment', copy=False)
    settlement_done = fields.Boolean(
        string='Settlement Completed', tracking=True, copy=False,
        help='Legacy "hal tammat al-taswiya" flag. Consumed by the clearance '
             'and final settlement process.')

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # CR 2.3 -- audit trail
    # ------------------------------------------------------------------
    # Stock hr.employee tracks almost nothing. These are the fields HR is
    # asked about in a dispute, so they get native tracking; everything else
    # is caught by the catch-all audit note in ``write`` below.
    name = fields.Char(tracking=True)
    job_id = fields.Many2one(tracking=True)
    job_title = fields.Char(tracking=True)
    department_id = fields.Many2one(tracking=True)
    parent_id = fields.Many2one(tracking=True)
    coach_id = fields.Many2one(tracking=True)
    work_email = fields.Char(tracking=True)
    work_phone = fields.Char(tracking=True)
    mobile_phone = fields.Char(tracking=True)
    company_id = fields.Many2one(tracking=True)

    # Fields whose changes are noise rather than audit: recomputed values,
    # attachments and the message stack itself.
    _AUDIT_EXCLUDE = {
        'write_date', 'write_uid', 'create_date', 'create_uid', '__last_update',
        'message_ids', 'message_follower_ids', 'activity_ids',
        'document_completeness', 'open_loan_balance', 'warning_count',
        'investigation_count', 'resignation_count', 'display_name',
    }

    # Child rows log their own CRUD operations, including direct ORM edits.
    _AUDIT_EXCLUDE_TYPES = {'one2many'}

    def _ibs_audit_fields(self, vals):
        """Stored, writable, non-tracked fields being changed by this write."""
        names = []
        for name in vals:
            field = self._fields.get(name)
            if not field or name in self._AUDIT_EXCLUDE:
                continue
            if not field.store or field.compute or field.related:
                continue
            if field.type in self._AUDIT_EXCLUDE_TYPES:
                continue
            if getattr(field, 'tracking', False):
                continue  # native tracking already logs it
            names.append(name)
        return names

    def _ibs_format_audit(self, field, value):
        if field.type in ('binary', 'image'):
            if not value:
                return _('No file')
            payload = value.encode() if isinstance(value, str) else value
            return _('File fingerprint: %s', hashlib.sha256(payload).hexdigest()[:16])
        if field.type == 'many2many':
            return ', '.join(value.mapped('display_name')) or '—'
        if field.type == 'many2one':
            return value.display_name or '—' if value else '—'
        if field.type == 'boolean':
            return _('Yes') if value else _('No')
        if value is False or value is None or value == '':
            return '—'
        if field.type == 'selection':
            return dict(field._description_selection(self.env)).get(value, value)
        text = str(value)
        # Keep the complete value for an audit rather than a shortened preview.
        return text

    def _ibs_post_audit(self, before):
        # ``message_post`` escapes a plain string body, so the note has to be
        # built as Markup or the reader gets the tags instead of the layout.
        # Values go through ``escape`` on the way in: a field holding '<' would
        # otherwise break the markup it lands in.
        for record in self:
            rows = []
            for name, old in before.get(record.id, {}).items():
                field = record._fields[name]
                new = record[name]
                if old == new:
                    continue
                rows.append(Markup('<li><b>%s</b>: %s &rarr; %s</li>') % (
                    field.string,
                    record._ibs_format_audit(field, old),
                    record._ibs_format_audit(field, new)))
            if rows:
                record.message_post(
                    body=Markup('<p>%s</p><ul>%s</ul>') % (
                        _('Employee record updated'),
                        Markup('').join(rows)))

    # ------------------------------------------------------------------
    # Migration bookkeeping
    # ------------------------------------------------------------------
    legacy_id = fields.Integer(
        string='Legacy ID', index=True, copy=False,
        help='Primary key in the source MariaDB users table.')
    legacy_odoo_id = fields.Integer(
        string='Legacy odoo_id', copy=False,
        help='Value the legacy application already stored in users.odoo_id '
             'while syncing to an earlier Odoo instance.')

    _sql_constraints = [
        ('employee_code_uniq', 'unique(employee_code)',
         'This employee code is already in use.'),
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another employee already carries this legacy ID.'),
    ]

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------
    def _compute_dependant_count(self):
        data = self.env['ellithy.hr.dependant']._read_group(
            [('employee_id', 'in', self.ids)], ['employee_id'], ['__count'])
        mapped = {employee.id: count for employee, count in data}
        for record in self:
            record.dependant_count = mapped.get(record.id, 0)

    @api.depends('document_ids.received', 'document_ids.type_id.required')
    def _compute_document_completeness(self):
        required_types = self.env['ellithy.hr.document.type'].search_count(
            [('required', '=', True)])
        for record in self:
            if not required_types:
                record.document_completeness = 100.0
                continue
            received = len(record.document_ids.filtered(
                lambda line: line.received and line.type_id.required))
            record.document_completeness = 100.0 * received / required_types

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------
    @api.constrains('active', 'resignation_date', 'last_working_day')
    def _check_departure_dates(self):
        """Reproduce the legacy ``check_inactive_dates`` database trigger.

        The source database refuses to deactivate an employee without both a
        resignation date and a last working day, and refuses to hold either
        date while the employee is still active.

        Historical data predates the trigger: 340 archived employees in the
        source carry neither date. Migration therefore runs with
        ``ellithy_migration=True`` in the context, which skips this check so
        those rows can land and be reported for HR to complete. The rule
        still applies to everything created afterwards -- the exemption is
        for the backlog, not a general relaxation.
        """
        if self.env.context.get('ellithy_migration'):
            return
        for record in self:
            if not record.active and not (
                    record.resignation_date and record.last_working_day):
                raise ValidationError(_(
                    'Cannot archive %(name)s without both a resignation date '
                    'and a last working day.',
                    name=record.name or ''))
            if record.active and (
                    record.resignation_date or record.last_working_day):
                raise ValidationError(_(
                    'Cannot set a resignation date or last working day on '
                    '%(name)s while the employee is still active.',
                    name=record.name or ''))

    @api.constrains('section_id', 'department_id')
    def _check_section_department(self):
        for record in self:
            if record.section_id and record.department_id and \
                    record.section_id.parent_id and \
                    record.section_id.parent_id != record.department_id:
                raise ValidationError(_(
                    'Section %(section)s does not belong to department '
                    '%(department)s.',
                    section=record.section_id.display_name,
                    department=record.department_id.display_name))

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        # During migration the code comes from the source system. Generating
        # one here would hand a migrated employee a fresh number that collides
        # with a legacy code further down the import, so leave it blank and
        # let the loader bump the sequence past the imported range afterwards.
        migrating = self.env.context.get('ellithy_migration')
        for vals in vals_list:
            if not vals.get('employee_code') or vals['employee_code'] == _('New'):
                vals['employee_code'] = False if migrating else (
                    self.env['ir.sequence'].next_by_code(
                        'ellithy.hr.employee.code') or _('New'))
        for vals in vals_list:
            self._normalise_employee_code(vals)
        employees = super().create(vals_list)
        employees._sync_document_lines()
        return employees

    def write(self, vals):
        self._normalise_employee_code(vals)
        # CR 2.3 -- capture the before image of anything Odoo will not track
        # for us, so the log notes carry the full history.
        audited = (
            [] if self.env.context.get('ellithy_migration')
            else self._ibs_audit_fields(vals))
        before = (
            {record.id: {name: record[name] for name in audited}
             for record in self} if audited else {})
        result = super().write(vals)
        if before:
            self._ibs_post_audit(before)
        return result

    @staticmethod
    def _normalise_employee_code(vals):
        """Store employee codes upper case.

        The unique constraint is case-sensitive, so without this 'EMP-950'
        and 'emp-950' are two different codes for what everyone reading a
        screen would call the same employee. Normalising on the way in makes
        the existing constraint enforce case-insensitive uniqueness, and the
        migrated data already satisfies it -- all 1,248 codes are upper case
        with no case-variant collisions.
        """
        code = vals.get('employee_code')
        if isinstance(code, str):
            vals['employee_code'] = code.strip().upper() or False


    # ------------------------------------------------------------------
    # CR 2.5 -- the welcome mail
    # ------------------------------------------------------------------
    # Sent from a button rather than on create. Creating an employee record
    # and welcoming a person are not the same act: a record is often opened
    # days before the joiner starts, corrected twice, or created in bulk from
    # an import -- none of which should put mail in someone's inbox. HR now
    # decides when, sees exactly what goes out, and can edit it first.
    welcome_email_sent = fields.Boolean(
        string='Welcome Email Sent', readonly=True, copy=False,
        help='Set once the onboarding mail has gone out. The button hides '
             'itself afterwards so nobody is welcomed twice.')
    welcome_email_sent_on = fields.Datetime(
        string='Welcome Email Sent On', readonly=True, copy=False)
    welcome_email_sent_by = fields.Many2one(
        'res.users', string='Welcome Email Sent By', readonly=True,
        copy=False)

    def action_send_welcome_mail(self):
        """Open the onboarding mail for review before it is sent."""
        self.ensure_one()
        if self.welcome_email_sent:
            raise ValidationError(_(
                'The onboarding mail has already been sent to %(name)s '
                'on %(date)s.', name=self.name,
                date=self.welcome_email_sent_on))
        if not self.work_email:
            raise ValidationError(_(
                'Set a work email on %(name)s before sending the onboarding '
                'mail -- there is nowhere to send it.', name=self.name))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send Onboarding Mail'),
            'res_model': 'ellithy.hr.welcome.mail.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

    def _sync_document_lines(self):
        """Give every employee one line per active document type."""
        types = self.env['ellithy.hr.document.type'].search([])
        for record in self:
            existing = record.document_ids.mapped('type_id')
            missing = types - existing
            if missing:
                record.document_ids = [
                    (0, 0, {'type_id': document_type.id})
                    for document_type in missing
                ]

    # ------------------------------------------------------------------
    # Display name and search
    # ------------------------------------------------------------------
    def _compute_display_name(self):
        """Show the employee code alongside the name.

        The code is the identifier the business actually uses -- it is the
        first column on every legacy screen -- so a bare name in a Many2one
        leaves you unable to tell EMP-5 from EMP-50 after searching for one.
        The bracketed form follows Odoo's own product convention.

        Stock ``hr.employee._compute_display_name`` delegates to
        ``hr.employee.public`` when the user cannot read employees; that model
        prefixes the code itself, so this returns early rather than adding it
        twice.
        """
        super()._compute_display_name()
        if not self.browse().has_access('read'):
            return
        for employee in self:
            if employee.employee_code:
                employee.display_name = (
                    f'[{employee.employee_code}] {employee.display_name}')

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """Rank an exact employee-code match first.

        ``_rec_names_search`` makes the code searchable, but it matches with
        ``ilike``: typing "EMP-5" returns EMP-50 and EMP-512 alongside the one
        you meant, in arbitrary order. Since the code is the identifier people
        actually type into an assignment field, an exact hit belongs at the
        top of the list rather than somewhere in it.
        """
        results = super().name_search(name, args, operator, limit)
        term = (name or '').strip()
        if not term or operator not in ('ilike', 'like', '=ilike', '=like'):
            return results

        exact = self.search(
            (args or []) + [('employee_code', '=ilike', term)], limit=1)
        if not exact:
            return results

        head = (exact.id, exact.display_name)
        rest = [row for row in results if row[0] != exact.id]
        combined = [head] + rest
        return combined[:limit] if limit else combined

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_force_logout(self):
        """Drop every active web session for the linked user.

        Odoo publishes no supported force-logout API: a session stays valid
        while ``id``, ``login``, ``password`` and ``active`` are unchanged
        (``res.users._get_session_token_fields``). The only way to end a
        session without archiving the user or resetting their password is to
        delete it from the session store directly, which is what this does.

        Because it reaches into ``odoo.http`` internals, it is deliberately
        defensive: on a deployment using a non-filesystem session store it
        reports failure rather than silently pretending the user was logged
        out. Verify this behaves as expected on your deployment before
        relying on it.
        """
        self.ensure_one()
        if not self.user_id:
            raise ValidationError(_(
                '%(name)s has no linked login to sign out.', name=self.name))

        killed = 0
        try:
            from odoo.http import root
            store = root.session_store
            for sid in store.list():
                session = store.get(sid)
                if session.get('uid') == self.user_id.id:
                    store.delete(session)
                    killed += 1
        except Exception as error:  # noqa: BLE001 - surfaced to the user
            raise ValidationError(_(
                'Could not reach the session store: %(error)s',
                error=error)) from error

        self.message_post(body=_(
            'Forced sign-out: %(count)s session(s) ended.', count=killed))
        return True


class HrEmployeePublic(models.Model):
    """Public employee view.

    ``hr.employee.public`` is a SQL view over ``hr_employee`` whose columns
    come from the fields declared on the model, so the code and Arabic name
    have to be declared here to appear at all. Without this, anyone without
    read access on employees sees a different display format from everyone
    else, and cannot search by code.
    """

    _inherit = 'hr.employee.public'

    _rec_names_search = ['name', 'employee_code', 'name_ar', 'work_email']

    employee_code = fields.Char(readonly=True)
    name_ar = fields.Char(readonly=True)

    def _compute_display_name(self):
        super()._compute_display_name()
        for employee in self:
            if employee.employee_code:
                employee.display_name = (
                    f'[{employee.employee_code}] {employee.display_name}')
