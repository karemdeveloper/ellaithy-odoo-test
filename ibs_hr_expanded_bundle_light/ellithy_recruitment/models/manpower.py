from odoo import _, api, fields, models
from odoo.exceptions import UserError


class ManpowerRequest(models.Model):
    """A department's headcount gap for one position, tracked to closure.

    "Required" is the headcount the department needs in that position;
    "current" counts the active employees in it today, so the shortage
    closes by itself as people are hired.
    """

    _name = 'ellithy.manpower.request'
    _description = 'Manpower Shortage'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'state_order, priority desc, date desc, id desc'

    name = fields.Char(
        string='Reference', required=True, copy=False, readonly=True,
        default=lambda self: _('New'))
    department_id = fields.Many2one(
        'hr.department', string='Department', required=True, tracking=True)
    job_id = fields.Many2one(
        'hr.job', string='Job Position', required=True, tracking=True)
    branch_id = fields.Many2one('ellithy.branch', string='Branch', tracking=True)
    required_count = fields.Integer(
        string='Required Headcount', required=True, default=1, tracking=True)
    current_count = fields.Integer(
        string='Current Headcount', compute='_compute_counts')
    shortage = fields.Integer(string='Shortage', compute='_compute_counts')
    pipeline_count = fields.Integer(
        string='Open Applications', compute='_compute_counts')
    reason = fields.Selection(
        [('new', 'New position'), ('replacement', 'Replacement'),
         ('expansion', 'Expansion / new branch'), ('other', 'Other')],
        default='replacement', required=True)
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'High'), ('2', 'Urgent')], default='0')
    date = fields.Date(default=fields.Date.context_today, required=True)
    target_date = fields.Date(string='Needed By')
    requested_by_id = fields.Many2one(
        'hr.employee', string='Requested By',
        default=lambda self: self.env.user.employee_id)
    state = fields.Selection(
        [('draft', 'Draft'), ('open', 'Open'), ('filled', 'Filled'),
         ('cancel', 'Cancelled')],
        default='draft', required=True, tracking=True)
    state_order = fields.Integer(compute='_compute_state_order', store=True)
    notes = fields.Text()
    company_id = fields.Many2one(
        'res.company', default=lambda self: self.env.company, required=True)

    @api.depends('state')
    def _compute_state_order(self):
        order = {'open': 0, 'draft': 1, 'filled': 2, 'cancel': 3}
        for request in self:
            request.state_order = order.get(request.state, 9)

    @api.depends('job_id', 'department_id', 'branch_id', 'required_count')
    def _compute_counts(self):
        Employee = self.env['hr.employee']
        Applicant = self.env['hr.applicant']
        for request in self:
            domain = [('job_id', '=', request.job_id.id)]
            if request.department_id:
                domain.append(('department_id', 'child_of', request.department_id.id))
            if request.branch_id:
                domain.append(('branch_id', '=', request.branch_id.id))
            current = Employee.search_count(domain) if request.job_id else 0
            request.current_count = current
            request.shortage = max(request.required_count - current, 0)
            request.pipeline_count = Applicant.search_count([
                ('job_id', '=', request.job_id.id),
                ('application_status', '=', 'ongoing'),
            ]) if request.job_id else 0

    @api.onchange('job_id')
    def _onchange_job_id(self):
        if self.job_id.department_id and not self.department_id:
            self.department_id = self.job_id.department_id

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'ellithy.manpower.request') or _('New')
        return super().create(vals_list)

    def action_open(self):
        """Open the request and set the job's recruitment target to the gap."""
        for request in self:
            if request.required_count <= 0:
                raise UserError(_('The required headcount must be positive.'))
            request.state = 'open'
            if request.shortage:
                request.job_id.no_of_recruitment = max(
                    request.job_id.no_of_recruitment, request.shortage)

    def action_mark_filled(self):
        self.write({'state': 'filled'})

    def action_cancel(self):
        self.write({'state': 'cancel'})

    def action_reset(self):
        self.write({'state': 'draft'})

    def action_view_applications(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window', 'name': _('Applications'),
            'res_model': 'hr.applicant', 'view_mode': 'kanban,list,form',
            'domain': [('job_id', '=', self.job_id.id)],
            'context': {'default_job_id': self.job_id.id},
        }
