from odoo import fields, models


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
