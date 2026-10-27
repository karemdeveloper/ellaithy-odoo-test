from odoo import _, api, fields, models

STATE = [
    ('draft', 'Draft'),
    ('open', 'Open'),
    ('closed', 'Closed'),
]


class IbsHrInvestigation(models.Model):
    """A disciplinary investigation, covering one or more employees."""

    _name = 'ibs.hr.investigation'
    _description = 'Investigation'
    _inherit = ['mail.thread']
    _order = 'date desc, id desc'

    name = fields.Char(string='Title', required=True, tracking=True)
    reference = fields.Char(
        copy=False, readonly=True, default=lambda self: _('New'))
    date = fields.Date(
        required=True, default=fields.Date.context_today, tracking=True)
    reason = fields.Text(string='Reason')
    notes = fields.Text()
    result = fields.Text(string='Result')
    action_taken = fields.Text(string='Action Taken')
    state = fields.Selection(STATE, default='draft', required=True,
                            tracking=True)

    employee_ids = fields.One2many(
        'ibs.hr.investigation.employee', 'investigation_id',
        string='Employees Involved')
    employee_count = fields.Integer(
        compute='_compute_employee_count', store=True)
    attachment_ids = fields.Many2many('ir.attachment', string='Files')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('legacy_id_uniq', 'unique(legacy_id)',
         'Another investigation already carries this legacy ID.'),
    ]

    @api.depends('employee_ids')
    def _compute_employee_count(self):
        for record in self:
            record.employee_count = len(record.employee_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('reference', _('New')) == _('New'):
                vals['reference'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.investigation') or _('New')
        return super().create(vals_list)

    def action_open(self):
        self.filtered(lambda r: r.state == 'draft').write({'state': 'open'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_reset(self):
        self.write({'state': 'draft'})


class IbsHrInvestigationEmployee(models.Model):
    """One employee's involvement in an investigation, with their outcome."""

    _name = 'ibs.hr.investigation.employee'
    _description = 'Investigation Employee'
    _order = 'investigation_id, id'

    investigation_id = fields.Many2one(
        'ibs.hr.investigation', required=True, ondelete='cascade', index=True)
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True, ondelete='restrict',
        index=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, string='Branch')
    result = fields.Text(string='Result')
    legacy_id = fields.Integer(string='Legacy ID', index=True, copy=False)

    _sql_constraints = [
        ('investigation_employee_uniq', 'unique(investigation_id, employee_id)',
         'That employee is already listed on this investigation.'),
    ]
