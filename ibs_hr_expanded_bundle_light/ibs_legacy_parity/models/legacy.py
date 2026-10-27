from datetime import timedelta
from math import ceil
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

PRIORITIES = [('low','Low'),('medium','Medium'),('high','High'),('urgent','Urgent')]
STATES = [('not_started','Not Started'),('in_progress','In Progress'),('on_hold','On Hold'),('cancelled','Cancelled'),('completed','Completed')]

class IBSLegacyProject(models.Model):
    _name = 'ibs.legacy.project'
    _description = 'Legacy HR Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    client_id = fields.Many2one('res.partner', string='Client')
    start_date = fields.Date()
    deadline = fields.Date(tracking=True)
    cost = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    estimated_hours = fields.Float()
    status = fields.Selection(STATES, default='not_started', required=True, tracking=True)
    priority = fields.Selection(PRIORITIES, default='medium')
    description = fields.Html()
    active = fields.Boolean(default=True)
    leader_ids = fields.Many2many('hr.employee', 'ibs_project_leader_rel', 'project_id', 'employee_id')
    member_ids = fields.Many2many('hr.employee', 'ibs_project_member_rel', 'project_id', 'employee_id')
    task_ids = fields.One2many('ibs.legacy.task', 'project_id')
    progress = fields.Integer(compute='_compute_progress')
    @api.depends('task_ids.status', 'task_ids.active')
    def _compute_progress(self):
        for rec in self:
            tasks = rec.task_ids.filtered('active')
            rec.progress = ceil(100 * len(tasks.filtered(lambda t: t.status == 'completed')) / len(tasks)) if tasks else 0
    @api.constrains('start_date','deadline')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.deadline and rec.deadline < rec.start_date:
                raise ValidationError(_('Deadline cannot precede start date.'))

class IBSLegacyTask(models.Model):
    _name = 'ibs.legacy.task'
    _description = 'Legacy HR Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    name = fields.Char(required=True, tracking=True)
    project_id = fields.Many2one('ibs.legacy.project', required=True, ondelete='cascade', index=True)
    priority = fields.Selection(PRIORITIES, default='medium')
    status = fields.Selection(STATES, default='not_started', required=True, tracking=True)
    start_date = fields.Date()
    end_date = fields.Date(tracking=True)
    description = fields.Html()
    active = fields.Boolean(default=True)
    member_ids = fields.Many2many('hr.employee', 'ibs_task_member_rel', 'task_id', 'employee_id')
    checklist_ids = fields.One2many('ibs.legacy.task.checklist', 'task_id')
    progress = fields.Integer(compute='_compute_progress')
    reminder_sent_date = fields.Date(copy=False, readonly=True)
    @api.depends('checklist_ids.is_completed', 'status')
    def _compute_progress(self):
        for rec in self:
            checks = rec.checklist_ids
            rec.progress = ceil(100 * len(checks.filtered('is_completed')) / len(checks)) if checks else (100 if rec.status == 'completed' else 0)
    @api.constrains('start_date','end_date')
    def _check_dates(self):
        for rec in self:
            if rec.start_date and rec.end_date and rec.end_date < rec.start_date:
                raise ValidationError(_('End date cannot precede start date.'))
    @api.model
    def _cron_remind_due_tasks(self):
        tomorrow = fields.Date.context_today(self) + timedelta(days=1)
        tasks = self.search([('end_date','=',tomorrow),('active','=',True),('status','not in',['cancelled','completed']),('reminder_sent_date','!=',fields.Date.context_today(self))])
        for task in tasks:
            emails = set(task.member_ids.mapped('work_email'))
            emails.update(task.project_id.leader_ids.mapped('work_email'))
            emails.discard(False)
            if emails:
                body = _('<p>Task <strong>%s</strong> is due on %s.</p>') % (task.name, task.end_date)
                self.env['mail.mail'].sudo().create({'subject': _('Task reminder: %s') % task.name, 'body_html': body, 'email_to': ','.join(sorted(emails))}).send()
            task.reminder_sent_date = fields.Date.context_today(self)

class IBSLegacyChecklist(models.Model):
    _name = 'ibs.legacy.task.checklist'
    _description = 'Legacy HR Task Checklist'
    name = fields.Char(required=True)
    task_id = fields.Many2one('ibs.legacy.task', required=True, ondelete='cascade')
    is_completed = fields.Boolean(default=False)
    assigned_to = fields.Many2one('hr.employee')
    deadline = fields.Date()

class IBSLegacyKpiPoint(models.Model):
    _name = 'ibs.legacy.kpi.point'
    _description = 'Job / Task / Behaviour KPI Point'
    name = fields.Char(required=True)
    category = fields.Selection([('job','Job'),('task','Task'),('behavior','Behavior')],required=True,default='job')
    job_id = fields.Many2one('hr.job')
    evaluator_id = fields.Many2one('hr.employee')
    target = fields.Float()
    weight = fields.Float(default=1.0)
    calculation_name = fields.Char()
    trend = fields.Selection([('higher','Higher Is Better'),('lower','Lower Is Better')],default='higher')
    type = fields.Selection([('number','Number'),('time','Time'),('percentage','Percentage')],default='number')
    unit = fields.Char()
    scope = fields.Char()
    is_weight_hold = fields.Boolean()
    original_weight = fields.Float()
    active = fields.Boolean(default=True)
    @api.constrains('weight')
    def _check_weight(self):
        for rec in self:
            if rec.weight < 0:
                raise ValidationError(_('KPI weight must be nonnegative.'))

class IBSLegacyKpiEvaluation(models.Model):
    _name = 'ibs.legacy.kpi.evaluation'
    _description = 'Monthly KPI Evaluation'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    point_id = fields.Many2one('ibs.legacy.kpi.point', required=True)
    employee_id = fields.Many2one('hr.employee', required=True)
    evaluator_id = fields.Many2one('hr.employee')
    month = fields.Selection([(str(x),str(x)) for x in range(1,13)], required=True)
    year = fields.Integer(required=True, default=lambda self: fields.Date.today().year)
    actual = fields.Float()
    calculation_value = fields.Float()
    percentage = fields.Float()
    remarks = fields.Text()
    attachment_ids = fields.Many2many('ir.attachment')
    _sql_constraints = [('unique_period_point_employee','unique(point_id,employee_id,month,year)','Only one evaluation for each KPI, employee and period is allowed.')]
