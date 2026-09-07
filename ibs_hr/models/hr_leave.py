from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class HrLeaveType(models.Model):
    """Leave type.

    Odoo covers name, paid/unpaid, allocation and approval natively. Only the
    legacy's own identifiers and the early-exit flag need carrying across.
    """

    _inherit = 'hr.leave.type'

    name_ar = fields.Char(string='Arabic Name')
    slug = fields.Char(
        string='Legacy Slug', index=True,
        help='Stable identifier from the legacy leave_types table.')
    legacy_allocated = fields.Integer(
        string='Legacy Allocation (days)',
        help='Default days the legacy system granted. Kept for reconciliation; '
             'the live figure is the Odoo allocation.')
    early_exit = fields.Boolean(
        string='Allows Early Exit',
        help='Legacy early_exit flag on the leave type.')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)


class HrLeave(models.Model):
    """Leave request.

    Most of the legacy columns already have a stock equivalent -- dates,
    duration, employee, state, description and attachments. What is missing is
    the second approval level and a handful of routing fields, which are added
    here rather than reinvented.
    """

    _inherit = 'hr.leave'

    title = fields.Char(string='Title')
    requires_admin_approval = fields.Boolean(
        string='Requires Admin Approval',
        help='Legacy flag marking a request that needs a second sign-off '
             'beyond the manager.')
    admin_second_approval_status = fields.Selection(
        [('pending', 'Pending'), ('approved', 'Approved'),
         ('rejected', 'Rejected')],
        string='Admin Second Approval')
    admin_second_approved_by = fields.Many2one(
        'res.users', string='Second Approver', readonly=True)
    admin_second_approved_at = fields.Datetime(
        string='Second Approved At', readonly=True)
    admin_remark = fields.Text(string='Admin Remark')
    early_exit = fields.Boolean(string='Early Exit')
    referred_by = fields.Many2one('hr.employee', string='Referred By')
    request_updated_by = fields.Many2one(
        'res.users', string='Updated By', readonly=True)
    leave_requested_date = fields.Datetime(
        string='Requested On',
        help='When the employee submitted the request, as opposed to when the '
             'leave itself starts.')
    official_holiday_id = fields.Many2one(
        'resource.calendar.leaves', string='Official Holiday',
        help='Set when the request was generated from a public holiday.')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another leave request already carries this legacy ID.'),
    ]


class HrLeaveTypeAnnual(models.Model):
    """Marks the leave type the annual entitlement rule applies to.

    The rule is about one specific type, and which one it is cannot be
    guessed from the name -- the legacy platform carried Arabic names and a
    slug, and a live database may hold more than one candidate. So it is a
    flag HR sets once, in Configuration.
    """

    _inherit = 'hr.leave.type'

    is_annual_entitlement = fields.Boolean(
        string='Statutory Annual Leave',
        help='Tick on the leave type that carries the statutory annual '
             'entitlement. Allocations of this type are pre-filled from the '
             "employee's length of service.")


class HrEmployeeAnnualLeave(models.Model):
    """CR 2.6 -- how many days of annual leave an employee is entitled to.

    Three tiers, in increasing order of seniority:

      * first year of employment      -> 15 days
      * thereafter                    -> 21 days
      * 10 years of INSURED service   -> 30 days

    The last tier is the one the requirement warns about. It is measured
    from ``social_insurance_start_date``, not from the joining date, because
    insured service is portable: an employee who arrives with nine years of
    insured service behind them reaches 30 days in their second year here,
    and the first-year default must not quietly hold them at 15.

    The figures are system parameters, not constants, because they are
    policy: the Egyptian Labour Law numbers can change without a code
    release, and HR should not need one.
    """

    _inherit = 'hr.employee'

    annual_leave_entitlement = fields.Float(
        string='Annual Leave Entitlement', digits=(4, 1),
        compute='_compute_annual_leave_entitlement',
        help='Statutory annual leave days for this employee today, given '
             'length of service and insured service.')

    @api.model
    def _annual_leave_params(self):
        get = self.env['ir.config_parameter'].sudo().get_param

        def number(key, default):
            try:
                return float(get(key, default))
            except (TypeError, ValueError):
                return float(default)

        return {
            'first_year_days': number('ibs_hr.annual_leave_first_year_days', 15),
            'standard_days': number('ibs_hr.annual_leave_standard_days', 21),
            'long_service_days': number(
                'ibs_hr.annual_leave_long_service_days', 30),
            'long_service_years': number(
                'ibs_hr.annual_leave_long_service_years', 10),
        }

    def _annual_leave_days(self, on_date=None):
        """Entitlement in days as at ``on_date`` (today by default)."""
        self.ensure_one()
        params = self._annual_leave_params()
        on_date = on_date or fields.Date.context_today(self)

        # Long service wins outright: it is the tier CR 2.6 asks us not to
        # undercut with the first-year default.
        insured_from = self.social_insurance_start_date
        if insured_from:
            insured_years = relativedelta(on_date, insured_from).years
            if insured_years >= params['long_service_years']:
                return params['long_service_days']

        # Without a joining date there is no first year to be inside, so the
        # standard entitlement applies; assuming the reduced one would
        # understate it on the strength of missing data.
        joined = self.joining_date
        if joined and on_date < joined + relativedelta(years=1):
            return params['first_year_days']
        return params['standard_days']

    def _compute_annual_leave_entitlement(self):
        for employee in self:
            employee.annual_leave_entitlement = (
                employee._annual_leave_days() if employee.id else 0.0)


class HrLeaveAllocation(models.Model):
    """Pre-fills a statutory annual allocation with the CR 2.6 entitlement.

    Only a suggestion: HR can still type a different figure, which is what
    makes carried-over balances and negotiated extras possible. The number
    is filled in on change of employee or leave type, so it follows a
    correction rather than sticking to whatever was first chosen.
    """

    _inherit = 'hr.leave.allocation'

    @api.onchange('employee_id', 'holiday_status_id')
    def _onchange_annual_entitlement(self):
        for allocation in self:
            leave_type = allocation.holiday_status_id
            if not leave_type.is_annual_entitlement or not allocation.employee_id:
                continue
            allocation.number_of_days = (
                allocation.employee_id._annual_leave_days())
