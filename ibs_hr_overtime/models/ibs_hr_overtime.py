import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


_WORKFLOW_TOKEN = object()

class IbsHrOvertime(models.Model):
    _name = 'ibs.hr.overtime'
    _description = 'Approved Overtime'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ellithy.hr.action.notification']
    _order = 'date desc, id desc'

    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='restrict')
    attendance_day_id = fields.Many2one(
        'ibs.hr.attendance.day', required=True, index=True, ondelete='restrict')
    date = fields.Date(related='attendance_day_id.date', store=True, index=True)
    candidate_minutes = fields.Integer(required=True, readonly=True)
    payable_minutes = fields.Integer(
        compute='_compute_payable_minutes', store=True)
    hourly_rate = fields.Monetary(compute='_compute_hourly_rate', store=True)
    multiplier = fields.Float(required=True, default=1.0)
    amount = fields.Monetary(compute='_compute_amount', store=True)
    currency_id = fields.Many2one(
        related='employee_id.company_id.currency_id', store=True)
    compensation = fields.Selection([
        ('cash', 'Cash'),
        ('rest', 'Compensatory Rest'),
    ], required=True, default='cash')
    rest_eligible = fields.Boolean(
        string='Rest Eligible', compute='_compute_rest_eligible')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('manager_approved', 'HR Generalist Approved'),
        ('approved', 'HR Approved'),
        ('paid', 'Paid'),
        ('rejected', 'Rejected'),
    ], required=True, default='draft', tracking=True)
    rejection_reason = fields.Text()
    rest_credit_id = fields.Many2one(
        'ibs.hr.rest.credit', readonly=True, ondelete='restrict')

    _sql_constraints = [
        ('attendance_day_unique', 'unique(attendance_day_id)',
         'Overtime already exists for this attendance day.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        if (not self.env.su
                and not self.env.context.get('ibs_overtime_generation') is _WORKFLOW_TOKEN):
            raise ValidationError(_(
                'Overtime records must be generated from attendance treatment.'))
        records = super().create(vals_list)
        records._notify_approval_group('ibs_hr_overtime.ibs_hr_overtime_generalist', _('Overtime awaiting HR approval'))
        return records

    def write(self, vals):
        if not self.env.su and self.env.context.get('ibs_overtime_transition') is not _WORKFLOW_TOKEN and self.env.context.get('ibs_overtime_generation') is not _WORKFLOW_TOKEN:
            if not self.env.user.has_group('ibs_hr_overtime.ibs_hr_overtime_generalist'):
                allowed = {'compensation'}
                if self.env.user.has_group('ibs_hr_overtime.ibs_hr_overtime_finance'):
                    allowed.add('rejection_reason')
                if set(vals) - allowed:
                    raise ValidationError(_('You may only select compensation for your own draft overtime.'))
        if (not self.env.su and {'state', 'rest_credit_id'}.intersection(vals)
                and not self.env.context.get('ibs_overtime_transition') is _WORKFLOW_TOKEN):
            raise ValidationError(_('Use the workflow actions to change status.'))
        immutable = {'employee_id', 'attendance_day_id', 'candidate_minutes'}
        if (not self.env.su and immutable.intersection(vals)
                and not self.env.context.get('ibs_overtime_generation') is _WORKFLOW_TOKEN):
            raise ValidationError(
                _('Overtime source values come from attendance treatment.'))
        if (not self.env.su and {'multiplier', 'compensation'}.intersection(vals)
                and any(overtime.state != 'draft' for overtime in self)):
            raise ValidationError(_('Approved overtime cannot be edited.'))
        return super().write(vals)

    def _require_group(self, xmlid):
        if not self.env.su and not self.env.user.has_group(xmlid):
            raise ValidationError(_('You are not authorized for this approval step.'))

    def _prevent_self_approval(self):
        if (not self.env.su and self.env.user.employee_id
                and self.employee_id == self.env.user.employee_id):
            raise ValidationError(_('You cannot approve your own overtime.'))

    @api.depends('candidate_minutes')
    def _compute_payable_minutes(self):
        for overtime in self:
            overtime.payable_minutes = (
                overtime.candidate_minutes
                if overtime.candidate_minutes >= 31 else 0)

    @api.depends('employee_id', 'attendance_day_id.scheduled_hours', 'date')
    def _compute_hourly_rate(self):
        for overtime in self:
            contract = overtime.employee_id.sudo()._ibs_contract_on(
                overtime.date) if overtime.employee_id and overtime.date else False
            daily_hours = overtime.attendance_day_id.scheduled_hours or 8.0
            overtime.hourly_rate = (
                contract.wage / 30.0 / daily_hours if contract else 0.0)

    @api.depends('payable_minutes', 'hourly_rate', 'multiplier', 'currency_id')
    def _compute_amount(self):
        for overtime in self:
            amount = (overtime.payable_minutes / 60.0
                      * overtime.hourly_rate * overtime.multiplier)
            overtime.amount = overtime.currency_id.round(amount)

    def _has_consecutive_worked_rest_day(self):
        self.ensure_one()
        if (not self.date or self.attendance_day_id.state not in
                ('weekend', 'holiday') or
                self.attendance_day_id.worked_hours <= 0):
            return False
        return bool(self.env['ibs.hr.attendance.day'].sudo().search_count([
            ('employee_id', '=', self.employee_id.id),
            ('date', 'in', [self.date - timedelta(days=1),
                            self.date + timedelta(days=1)]),
            ('state', 'in', ('weekend', 'holiday')),
            ('worked_hours', '>', 0.0),
        ]))

    @api.depends('attendance_day_id.state',
                 'attendance_day_id.worked_hours', 'date')
    def _compute_rest_eligible(self):
        for overtime in self:
            overtime.rest_eligible = (
                overtime._has_consecutive_worked_rest_day()
                if overtime.id else False)

    @api.constrains('candidate_minutes', 'multiplier')
    def _check_values(self):
        for overtime in self:
            if overtime.candidate_minutes < 0 or overtime.multiplier < 0:
                raise ValidationError(_('Overtime values cannot be negative.'))

    @api.model
    def generate_from_attendance(self, date_from=None, date_to=None):
        date_from = fields.Date.to_date(
            date_from or fields.Date.context_today(self))
        date_to = fields.Date.to_date(date_to or date_from)
        days = self.env['ibs.hr.attendance.day'].search([
            ('date', '>=', date_from), ('date', '<=', date_to),
        ])
        for day in days:
            hours = (day.worked_hours if day.state in ('weekend', 'holiday')
                     else day.overtime_hours)
            minutes = math.floor(hours * 60.0 + 1e-9)
            existing = self.search([
                ('attendance_day_id', '=', day.id),
            ], limit=1)
            if existing and existing.state == 'draft':
                existing.with_context(ibs_overtime_generation=_WORKFLOW_TOKEN).write({
                    'candidate_minutes': minutes})
            elif not existing and minutes >= 31:
                self.with_context(ibs_overtime_generation=_WORKFLOW_TOKEN).create({
                    'employee_id': day.employee_id.id,
                    'attendance_day_id': day.id,
                    'candidate_minutes': minutes,
                })
        return True

    def action_manager_approve(self):
        for overtime in self:
            overtime._require_group(
                'ibs_hr_overtime.ibs_hr_overtime_generalist')
            overtime._prevent_self_approval()
            if overtime.state != 'draft':
                raise UserError(_('Only draft overtime can be manager approved.'))
            if overtime.payable_minutes < 31:
                raise ValidationError(
                    _('Overtime must exceed 30 complete minutes.'))
            if (overtime.compensation == 'rest'
                    and not overtime._has_consecutive_worked_rest_day()):
                raise ValidationError(_(
                    'Compensatory rest requires work on consecutive weekend '
                    'or public-holiday days.'))
            overtime.with_context(ibs_overtime_transition=_WORKFLOW_TOKEN).write({
                'state': 'manager_approved'})
            overtime._notify_approval_group('ibs_hr_overtime.ibs_hr_overtime_finance',
                                            _('Overtime awaiting Finance approval'))

    def action_hr_approve(self):
        for overtime in self:
            overtime._require_group(
                'ibs_hr_overtime.ibs_hr_overtime_finance')
            overtime._prevent_self_approval()
            if overtime.state != 'manager_approved':
                raise UserError(_('Manager approval is required first.'))
            if (overtime.compensation == 'rest'
                    and not overtime._has_consecutive_worked_rest_day()):
                raise ValidationError(_(
                    'Compensatory rest requires work on consecutive weekend '
                    'or public-holiday days.'))
            values = {'state': 'approved'}
            if overtime.compensation == 'rest':
                credit = self.env['ibs.hr.rest.credit'].sudo().create({
                    'employee_id': overtime.employee_id.id,
                    'source_date': overtime.date,
                    'days': 1.0,
                    'attendance_day_id': overtime.attendance_day_id.id,
                })
                values['rest_credit_id'] = credit.id
            overtime.with_context(ibs_overtime_transition=_WORKFLOW_TOKEN).write(values)
            overtime._notify_employee(_('Overtime approved'))

    def action_reject(self):
        for overtime in self:
            group = ('ibs_hr_overtime.ibs_hr_overtime_finance'
                     if overtime.state == 'manager_approved'
                     else 'ibs_hr_overtime.ibs_hr_overtime_generalist')
            overtime._require_group(group)
            overtime._prevent_self_approval()
            if overtime.state not in ('draft', 'manager_approved'):
                raise UserError(_('Only overtime awaiting approval can be rejected.'))
            if not overtime.rejection_reason:
                raise ValidationError(_('Enter a rejection reason.'))
            overtime.with_context(ibs_overtime_transition=_WORKFLOW_TOKEN).write({
                'state': 'rejected'})

    @api.model
    def _cron_generate_overtime(self):
        yesterday = fields.Date.context_today(self) - timedelta(days=1)
        return self.generate_from_attendance(
            yesterday - timedelta(days=1), yesterday)
