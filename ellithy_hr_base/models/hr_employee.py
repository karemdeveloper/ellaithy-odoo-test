from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

VACATION_ROLE = [
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

MEDICAL_TIER = [
    ('a', 'A'),
    ('b', 'B'),
    ('c', 'C'),
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
        VACATION_ROLE, string='Vacation Role',
        help='Annual leave entitlement tier. Egyptian labour law grants 21 '
             'days, rising to 30 with long service or age.')
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
    # Medical insurance (employee side; dependants are a child model)
    # ------------------------------------------------------------------
    medical_insurance_date = fields.Date(string='Medical Insurance Date')
    medical_insurance_type = fields.Selection(
        MEDICAL_TIER, string='Medical Insurance Type')
    medical_card_number = fields.Char(string='Medical Card Number')
    medical_cost_per_year = fields.Monetary(
        string='Cost Per Year', currency_field='currency_id')
    medical_cost_per_month = fields.Monetary(
        string='Cost Per Month', currency_field='currency_id')
    medical_employee_share = fields.Float(
        string='Employee Share (%)', digits=(5, 2))
    has_medical_relative = fields.Boolean(string='Has Covered Relatives')
    dependant_ids = fields.One2many(
        'ellithy.hr.dependant', 'employee_id', string='Covered Relatives')
    dependant_count = fields.Integer(
        string='Relatives', compute='_compute_dependant_count')

    # ------------------------------------------------------------------
    # Social insurance
    #
    # Field order follows the legacy form: enrolment flag, office, number,
    # start date, then the three salary figures and the profession. The
    # salaries are related to the CURRENT contract rather than stored here --
    # editing them updates that contract, so a later raise creates a new
    # contract and leaves the old figures intact.
    # ------------------------------------------------------------------
    has_social_insurance = fields.Boolean(string='Has Social Insurance')
    social_insurance_office_id = fields.Many2one(
        'ellithy.hr.insurance.office', string='Social Insurance Office',
        ondelete='restrict')
    social_insurance_number = fields.Char(
        string='Social Insurance Number',
        help='Legacy users.social_insurance_number. Distinct from the older '
             'insurance_number column, which is kept below.')
    social_insurance_start_date = fields.Date(
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
    insurance_number = fields.Char(string='Insurance Number (legacy)')
    insurance_office = fields.Char(string='Insurance Office (legacy)')
    insurance_entered_date = fields.Date(string='Insurance Registration Date')
    insurance_salary = fields.Monetary(
        string='Insured Salary', currency_field='currency_id')
    social_insurance_price = fields.Monetary(
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
        return super().write(vals)

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
    def action_open_status_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Change Employee Status'),
            'res_model': 'ellithy.hr.employee.status.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_employee_id': self.id},
        }

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
