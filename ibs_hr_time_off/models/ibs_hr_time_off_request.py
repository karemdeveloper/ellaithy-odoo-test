from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_round


_WORKFLOW_TOKEN = object()

ACTIVE_STATES = ('submitted', 'manager_approved', 'approved')


class IbsHrTimeOffRequest(models.Model):
    _name = 'ibs.hr.time.off.request'
    _description = 'Time Off Request'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'ellithy.hr.action.notification']
    _order = 'date_from desc, id desc'

    name = fields.Char(
        string='Reference', required=True, readonly=True, copy=False,
        default=lambda self: _('New'))
    employee_id = fields.Many2one(
        'hr.employee', required=True, index=True, ondelete='restrict',
        tracking=True, default=lambda self: self.env.user.employee_id)
    company_id = fields.Many2one(
        related='employee_id.company_id', store=True, index=True)
    branch_id = fields.Many2one(
        related='employee_id.branch_id', store=True, index=True)
    type_id = fields.Many2one(
        'ibs.hr.time.off.type', required=True, ondelete='restrict', tracking=True)
    type_code = fields.Selection(related='type_id.code', readonly=True)
    approval_route = fields.Selection(
        related='type_id.approval_route', readonly=True)
    date_from = fields.Date(required=True, tracking=True)
    date_to = fields.Date(required=True, tracking=True)
    number_of_days = fields.Float(
        compute='_compute_number_of_days', store=True, digits=(8, 4))
    reason = fields.Text()
    attachment_ids = fields.Many2many(
        'ir.attachment', 'ibs_time_off_attachment_rel',
        'request_id', 'attachment_id', string='Attachments')
    holiday_id = fields.Many2one(
        'ibs.hr.public.holiday', string='Public Holiday', ondelete='restrict')
    rest_credit_id = fields.Many2one(
        'ibs.hr.rest.credit', string='Rest Credit', ondelete='restrict')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('manager_approved', 'HR Generalist Approved'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled'),
    ], required=True, default='draft', tracking=True)
    rejection_reason = fields.Text()
    balance = fields.Float(compute='_compute_balance', digits=(8, 4))
    manager_approved_by = fields.Many2one('res.users', readonly=True)
    hr_approved_by = fields.Many2one('res.users', readonly=True)

    def unlink(self):
        if not self.env.su and any(record.state not in ('draft',) for record in self):
            raise ValidationError(_('Only draft documents can be deleted.'))
        return super().unlink()

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            self._check_request_employee(values.get('employee_id', self.env.user.employee_id.id),
                                         'ibs_hr_time_off.ibs_hr_time_off_generalist')
            if not self.env.su and (values.get('state', 'draft') != 'draft'
                    or values.get('manager_approved_by') or values.get('hr_approved_by')):
                raise ValidationError(_('Create a draft request and use the approval actions.'))
            if values.get('name', _('New')) == _('New'):
                values['name'] = self.env['ir.sequence'].next_by_code(
                    'ibs.hr.time.off.request') or _('New')
        return super().create(vals_list)

    def write(self, vals):
        if 'employee_id' in vals:
            self._check_request_employee(vals['employee_id'],
                                         'ibs_hr_time_off.ibs_hr_time_off_generalist')
        protected = {'state', 'manager_approved_by', 'hr_approved_by'}
        business = {
            'employee_id', 'type_id', 'date_from', 'date_to', 'reason',
            'attachment_ids', 'holiday_id', 'rest_credit_id',
        }
        if (not self.env.su and protected.intersection(vals)
                and not self.env.context.get('ibs_time_off_transition') is _WORKFLOW_TOKEN):
            raise ValidationError(_('Use the workflow actions to change status.'))
        if (not self.env.su and business.intersection(vals)
                and any(request.state != 'draft' for request in self)
                and not self.env.context.get('ibs_time_off_transition') is _WORKFLOW_TOKEN):
            raise ValidationError(_('Return the request to Draft before editing it.'))
        return super().write(vals)

    def _require_group(self, xmlid):
        if not self.env.su and not self.env.user.has_group(xmlid):
            raise ValidationError(_('You are not authorized for this approval step.'))

    def _prevent_self_approval(self):
        if (not self.env.su and self.env.user.employee_id
                and self.employee_id == self.env.user.employee_id):
            raise ValidationError(_('You cannot approve your own request.'))

    @api.depends('employee_id', 'type_id', 'date_from', 'date_to')
    def _compute_number_of_days(self):
        holidays = self.env['ibs.hr.public.holiday'].sudo()
        for request in self:
            if not request.employee_id or not request.date_from or not request.date_to:
                request.number_of_days = 0.0
                continue
            if request.type_id.code in ('birthday', 'public_holiday',
                                        'compensatory_rest'):
                request.number_of_days = 1.0
                continue
            shift = request.employee_id.shift_id
            current = request.date_from
            days = 0
            while shift and current <= request.date_to:
                line = shift.line_ids.filtered(
                    lambda item: item.day == str(current.weekday()))[:1]
                is_holiday = holidays.search_count([
                    ('date', '=', current),
                    ('company_id', '=', request.employee_id.company_id.id),
                    ('active', '=', True),
                ])
                if line and not line.is_off and not is_holiday:
                    days += 1
                current += timedelta(days=1)
            request.number_of_days = float(days)

    @api.depends('employee_id', 'type_id', 'date_from')
    def _compute_balance(self):
        for request in self:
            request.balance = request._balance_on(
                request.date_from, ensure=False) if (
                request.employee_id and request.type_id and request.date_from) else 0.0

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for request in self:
            if request.date_from and request.date_to < request.date_from:
                raise ValidationError(_('To Date must be on or after From Date.'))

    def _lock_employee(self):
        self.env.flush_all()
        self.env.cr.execute(
            'UPDATE hr_employee SET id = id WHERE id = %s',
            [self.employee_id.id])

    def _service_period(self, on_date):
        self.ensure_one()
        joined = self.employee_id.joining_date
        if not joined:
            return False, False, 0
        years = max(relativedelta(on_date, joined).years, 0)
        start = joined + relativedelta(years=years)
        if start > on_date:
            start -= relativedelta(years=1)
            years -= 1
        return start, start + relativedelta(years=1), years

    def _calendar_accrual_events(self, on_date):
        """Accrue on monthly joining anniversaries, starting after 3 months."""
        self.ensure_one()
        joined = self.employee_id.joining_date
        start = on_date.replace(month=1, day=1)
        elapsed = relativedelta(start, joined)
        month = max(self.type_id.required_period_months,
                    elapsed.years * 12 + elapsed.months, 1)
        events = []
        cumulative = 0.0
        rounded = 0.0
        while True:
            due = joined + relativedelta(months=month)
            if due > on_date:
                break
            if due >= start:
                months = self.type_id.required_period_months if (
                    month == self.type_id.required_period_months) else 1
                cumulative += self.employee_id._annual_leave_days(due) * months / 12.0
                target = float_round(cumulative, precision_digits=4)
                events.append((due, float_round(target - rounded, precision_digits=4)))
                rounded = target
            month += 1
        return events

    def _retire_calendar_legacy_entries(self, on_date):
        """Replace the old service-year policy with separate audit postings."""
        self.ensure_one()
        ledger = self.env['ibs.hr.time.off.ledger'].sudo()
        legacy = ledger.search([
            ('employee_id', '=', self.employee_id.id),
            ('type_id', '=', self.type_id.id),
            ('date', '>=', on_date.replace(month=1, day=1)),
            ('date', '<=', on_date),
            ('entry_type', 'in', ('grant', 'accrual', 'adjustment'))])
        for entry in legacy.filtered(lambda item: item.unique_key and
                item.unique_key.startswith(('annual:', 'annual-eight-correction:', 'casual:'))):
            key = 'calendar-policy-reversal:%s' % entry.id
            if not ledger.search_count([('unique_key', '=', key)]):
                ledger.create({
                    'employee_id': self.employee_id.id, 'type_id': self.type_id.id,
                    'date': entry.date, 'amount': -entry.amount,
                    'entry_type': 'adjustment', 'unique_key': key,
                    'description': _('Calendar accrual policy replacement: posting %s') % entry.id,
                })

    def _ensure_entitlements(self, on_date):
        self.ensure_one()
        kind = self.type_id.code
        if kind not in ('casual', 'annual'):
            return
        joined = self.employee_id.joining_date
        if not joined:
            raise ValidationError(_('Set the employee Joining Date first.'))
        on_date = fields.Date.to_date(on_date)
        year_start = on_date.replace(month=1, day=1)
        ledger = self.env['ibs.hr.time.off.ledger'].sudo()
        expiry_key = 'calendar-expiry:%s:%s:%s' % (
            self.employee_id.id, self.type_id.id, year_start.year)
        if not ledger.search_count([('unique_key', '=', expiry_key)]):
            prior = ledger.search([
                ('employee_id', '=', self.employee_id.id),
                ('type_id', '=', self.type_id.id), ('date', '<', year_start)])
            amount = float_round(sum(prior.mapped('amount')), precision_digits=4)
            if prior:
                ledger.create({
                    'employee_id': self.employee_id.id, 'type_id': self.type_id.id,
                    'date': year_start, 'amount': -amount, 'entry_type': 'expiry',
                    'unique_key': expiry_key,
                    'description': _('Unused leave expires on 1 January'),
                })
        self._retire_calendar_legacy_entries(on_date)
        eligibility = joined + relativedelta(months=self.type_id.required_period_months)
        if on_date < eligibility:
            return
        if kind == 'casual':
            events = [(max(year_start, eligibility), self.type_id.limit_days)]
        else:
            events = self._calendar_accrual_events(on_date)
        for due, amount in events:
            key = 'calendar-%s:%s:%s:%s' % (
                kind, self.employee_id.id, self.type_id.id, due)
            existing = ledger.search([('unique_key', '=', key)], limit=1)
            if existing:
                continue
            ledger.create({
                'employee_id': self.employee_id.id, 'type_id': self.type_id.id,
                'date': due, 'amount': amount,
                'entry_type': 'grant' if kind == 'casual' else 'accrual',
                'description': _('Calendar-year casual grant') if kind == 'casual'
                               else _('Annual accrual on monthly joining anniversary'),
                'unique_key': key,
            })

    def _balance_on(self, on_date, ensure=True):
        self.ensure_one()
        if not self.employee_id or not self.type_id or not on_date:
            return 0.0
        on_date = fields.Date.to_date(on_date)
        if ensure:
            self._ensure_entitlements(on_date)
        domain = [
            ('employee_id', '=', self.employee_id.id),
            ('type_id', '=', self.type_id.id), ('date', '<=', on_date)]
        if self.type_id.code in ('annual', 'casual'):
            # Expiry records close the prior year's audit balance. Spendable
            # credit comes only from this year's grants, accruals and usage.
            domain += [('date', '>=', on_date.replace(month=1, day=1)),
                       ('entry_type', '!=', 'expiry')]
        return float_round(sum(self.env['ibs.hr.time.off.ledger'].sudo().search(
            domain).mapped('amount')), precision_digits=4)

    def _leave_days_by_year(self):
        self.ensure_one()
        result = {}
        shift = self.employee_id.shift_id
        current = self.date_from
        holidays = self.env['ibs.hr.public.holiday'].sudo()
        while shift and current <= self.date_to:
            line = shift.line_ids.filtered(
                lambda item: item.day == str(current.weekday()))[:1]
            holiday = holidays.search_count([
                ('date', '=', current),
                ('company_id', '=', self.employee_id.company_id.id),
                ('active', '=', True)])
            if line and not line.is_off and not holiday:
                bucket = result.setdefault(current.year, {'date': current, 'days': 0})
                bucket['days'] += 1
            current += timedelta(days=1)
        return result

    def _reserved_days(self, on_date=None):
        self.ensure_one()
        on_date = on_date or self.date_from
        requests = self.search([
            ('id', '!=', self.id), ('employee_id', '=', self.employee_id.id),
            ('type_id', '=', self.type_id.id),
            ('date_from', '<=', on_date.replace(month=12, day=31)),
            ('date_to', '>=', on_date.replace(month=1, day=1)),
            ('state', 'in', ('submitted', 'manager_approved'))])
        return sum(request._leave_days_by_year().get(
            on_date.year, {}).get('days', 0) for request in requests)

    def _validate_submission(self):
        self.ensure_one()
        self._lock_employee()
        if self.type_id.company_id != self.employee_id.company_id:
            raise ValidationError(_(
                'The Time Off Type and employee must belong to the same company.'))
        if self.number_of_days <= 0:
            raise ValidationError(_('The selected dates contain no working day.'))
        if self.type_id.code in ('birthday', 'public_holiday',
                                 'compensatory_rest') and self.date_from != self.date_to:
            raise ValidationError(_('This time off type must be exactly one day.'))
        joined = self.employee_id.joining_date
        if self.type_id.required_period_months:
            if not joined:
                raise ValidationError(_('Set the employee Joining Date first.'))
            eligible = joined + relativedelta(
                months=self.type_id.required_period_months)
            if self.date_from < eligible:
                raise ValidationError(_(
                    'This time off is available from %(date)s.', date=eligible))
        if self.type_id.has_attachment and not self.attachment_ids:
            raise ValidationError(_('An attachment is required for this type.'))
        if self.type_id.code == 'birthday':
            birthday = self.employee_id.birthday
            if not birthday or (self.date_from.month, self.date_from.day) != (
                    birthday.month, birthday.day):
                raise ValidationError(
                    _('Birthday Time Off must be taken on the employee birthday.'))
        overlap = self.search_count([
            ('id', '!=', self.id),
            ('employee_id', '=', self.employee_id.id),
            ('state', 'in', ACTIVE_STATES),
            ('date_from', '<=', self.date_to),
            ('date_to', '>=', self.date_from),
        ])
        if overlap:
            raise ValidationError(_('This request overlaps another time off.'))
        year_start = self.date_from.replace(month=1, day=1)
        year_end = self.date_from.replace(month=12, day=31)
        same_year = self.search([
            ('id', '!=', self.id),
            ('employee_id', '=', self.employee_id.id),
            ('type_id', '=', self.type_id.id),
            ('state', 'in', ACTIVE_STATES),
            ('date_from', '>=', year_start),
            ('date_from', '<=', year_end),
        ])
        if self.type_id.one_day_per_year and (
                self.number_of_days > 1 or same_year):
            raise ValidationError(_('This type can be used only once per year.'))
        if self.type_id.code == 'public_holiday':
            if not self.holiday_id:
                raise ValidationError(_('Select the Public Holiday.'))
            duplicate = self.search_count([
                ('id', '!=', self.id),
                ('employee_id', '=', self.employee_id.id),
                ('holiday_id', '=', self.holiday_id.id),
                ('state', 'in', ACTIVE_STATES),
            ])
            if duplicate:
                raise ValidationError(
                    _('This public holiday has already been used.'))
        if self.type_id.code == 'compensatory_rest':
            if not self.rest_credit_id or self.rest_credit_id.state != 'available':
                raise ValidationError(_('Select an available Rest Credit.'))
            duplicate_credit = self.search_count([
                ('id', '!=', self.id),
                ('rest_credit_id', '=', self.rest_credit_id.id),
                ('state', 'in', ACTIVE_STATES),
            ])
            if duplicate_credit:
                raise ValidationError(
                    _('This Rest Credit is already reserved by another request.'))
        if self.type_id.code in ('casual', 'annual'):
            for bucket in self._leave_days_by_year().values():
                date = bucket['date']
                available = self._balance_on(date) - self._reserved_days(date)
                if bucket['days'] > available:
                    raise ValidationError(_(
                        'Only %(days).4f days are available in %(year)s.',
                        days=available, year=date.year))
                limit = (self.employee_id._annual_leave_days(date)
                         if self.type_id.code == 'annual' else self.type_id.limit_days)
                if limit and bucket['days'] > limit:
                    raise ValidationError(_('The request exceeds the type day limit.'))
        elif self.type_id.limit_days and self.number_of_days > self.type_id.limit_days:
            raise ValidationError(_('The request exceeds the type day limit.'))
        if (self.type_id.code == 'other' and self.type_id.limit_days
                and self.number_of_days + sum(
                    same_year.mapped('number_of_days')) > self.type_id.limit_days):
            raise ValidationError(_(
                'This request exceeds the yearly limit for the type.'))

    def action_submit(self):
        for request in self:
            if request.state != 'draft':
                raise UserError(_('Only a draft request can be submitted.'))
            request._validate_submission()
            request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                'state': 'submitted'})
            request._notify_approval_group(
                'ibs_hr_time_off.ibs_hr_time_off_generalist', _('Time off awaiting HR approval'))

    def _post_usage(self):
        self.ensure_one()
        buckets = (self._leave_days_by_year() if self.type_id.code in ('annual', 'casual')
                   else {self.date_from.year: {
                       'date': self.date_from, 'days': self.number_of_days}})
        for year, bucket in buckets.items():
            self.env['ibs.hr.time.off.ledger'].sudo().create({
                'employee_id': self.employee_id.id, 'type_id': self.type_id.id,
                'date': bucket['date'], 'amount': -bucket['days'],
                'entry_type': 'usage', 'request_id': self.id,
                'description': self.name, 'unique_key': 'usage:%s:%s' % (self.id, year),
            })
        if self.rest_credit_id:
            self.rest_credit_id.sudo().write({'state': 'used', 'request_id': self.id})

    def _refresh_attendance(self):
        for request in self:
            self.env['ibs.hr.attendance.day'].sudo().generate_days(
                request.date_from, request.date_to, request.employee_id)
            if 'ibs.hr.overtime' in self.env:
                self.env['ibs.hr.overtime'].sudo().generate_from_attendance(
                    request.date_from, request.date_to)

    def action_manager_approve(self):
        for request in self:
            request._require_group(
                'ibs_hr_time_off.ibs_hr_time_off_generalist')
            request._prevent_self_approval()
            if request.state != 'submitted' or request.type_id.approval_route == 'hr':
                raise UserError(_('This request is not awaiting manager approval.'))
            if request.type_id.approval_route == 'manager':
                request._validate_submission()
                request._post_usage()
                request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                    'state': 'approved',
                    'manager_approved_by': self.env.user.id,
                })
                request._refresh_attendance()
                request._notify_employee(_('Time off approved'))
            else:
                request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                    'state': 'manager_approved',
                    'manager_approved_by': self.env.user.id,
                })
                request._notify_approval_group(
                    'ibs_hr_time_off.ibs_hr_time_off_admin', _('Time off awaiting HR Admin approval'))

    def action_hr_approve(self):
        for request in self:
            request._require_group(
                'ibs_hr_time_off.ibs_hr_time_off_admin' if request.approval_route == 'both'
                else 'ibs_hr_time_off.ibs_hr_time_off_generalist')
            request._prevent_self_approval()
            expected = ('submitted' if request.type_id.approval_route == 'hr'
                        else 'manager_approved')
            if request.state != expected:
                raise UserError(_('This request is not awaiting HR approval.'))
            request._validate_submission()
            request._post_usage()
            request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                'state': 'approved', 'hr_approved_by': self.env.user.id,
            })
            request._refresh_attendance()
            request._notify_employee(_('Time off approved'))

    def action_reject(self):
        for request in self:
            group = ('ibs_hr_time_off.ibs_hr_time_off_admin'
                     if request.state == 'manager_approved'
                     else 'ibs_hr_time_off.ibs_hr_time_off_generalist')
            request._require_group(group)
            request._prevent_self_approval()
            if request.state not in ('submitted', 'manager_approved'):
                raise UserError(_('Only a request awaiting approval can be rejected.'))
            if not request.rejection_reason:
                raise ValidationError(_('Enter a rejection reason.'))
            request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                'state': 'rejected'})
            request._notify_employee(_('Time off rejected'))

    def action_cancel(self):
        for request in self:
            if request.state == 'approved':
                request._require_group(
                    'ibs_hr_time_off.ibs_hr_time_off_generalist')
            if request.state == 'approved':
                ledger = self.env['ibs.hr.time.off.ledger'].sudo()
                for usage in ledger.search([
                        ('request_id', '=', request.id), ('entry_type', '=', 'usage')]):
                    ledger.create({
                        'employee_id': request.employee_id.id,
                        'type_id': request.type_id.id, 'date': usage.date,
                        'amount': -usage.amount, 'entry_type': 'reversal',
                        'request_id': request.id, 'description': _('Cancellation reversal'),
                        'unique_key': 'reversal:%s:%s' % (request.id, usage.id),
                    })
                if request.rest_credit_id:
                    request.rest_credit_id.sudo().write({
                        'state': 'available', 'request_id': False,
                    })
            request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                'state': 'cancelled'})
            request._notify_employee(_('Time off cancelled'))
            request._refresh_attendance()

    def action_reset_draft(self):
        for request in self:
            if request.state not in ('submitted', 'manager_approved',
                                     'rejected'):
                raise UserError(_('This request cannot be reset to draft.'))
            request.with_context(ibs_time_off_transition=_WORKFLOW_TOKEN).write({
                'state': 'draft'})

    @api.model
    def _cron_post_accruals(self):
        today = fields.Date.context_today(self)
        employees = self.env['hr.employee'].search([
            ('active', '=', True), ('joining_date', '!=', False),
        ])
        types = self.env['ibs.hr.time.off.type'].search([
            ('active', '=', True), ('code', 'in', ('casual', 'annual')),
        ])
        for employee in employees:
            for time_off_type in types.filtered(
                    lambda item: item.company_id == employee.company_id):
                request = self.new({
                    'employee_id': employee.id,
                    'type_id': time_off_type.id,
                    'date_from': today,
                    'date_to': today,
                })
                request._ensure_entitlements(today)
        return True
