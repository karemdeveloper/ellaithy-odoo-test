import math
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


HCM_CODES = (
    'TRA', 'JOB', 'Comm', 'Meal', 'OT100', 'SOCIN', 'MOB',
    'ABS', 'Late', 'Finger', 'UNPaid',
)
MANUAL_CODES = ('BONUS', 'HIring', 'Res')


_HCM_WORKFLOW = object()


class HrPayslip(models.Model):
    _name = 'hr.payslip'
    _inherit = ['hr.payslip', 'ellithy.hr.action.notification']

    def _ibs_outstanding_penalties(self):
        self.check_access('read')
        return super(HrPayslip, self.sudo())._ibs_outstanding_penalties()

    def _ibs_apply_penalty_plan(self):
        self._hcm_require_role('finance')
        self.check_access('write')
        return super(HrPayslip, self.sudo())._ibs_apply_penalty_plan()

    def _ibs_release_penalty_plan(self):
        self._hcm_require_role('admin')
        self.check_access('write')
        return super(HrPayslip, self.sudo())._ibs_release_penalty_plan()

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            self._hcm_require_role('generalist')
            if any(values.get('state', 'draft') != 'draft' for values in vals_list):
                raise ValidationError(_('Create a draft payslip and use the payroll actions.'))
        return super().create(vals_list)

    def write(self, vals):
        if not self.env.su and 'state' in vals and self.env.context.get('hcm_workflow') is not _HCM_WORKFLOW:
            raise ValidationError(_('Use the payroll actions to change status.'))
        if not self.env.su and {'employee_id', 'contract_id', 'date_from', 'date_to',
                               'struct_id', 'input_line_ids', 'worked_days_line_ids',
                               'line_ids'}.intersection(vals):
            self._hcm_require_role('generalist')
            if any(record.state == 'done' for record in self):
                raise ValidationError(_('Reset a finalized payslip before editing it.'))
        return super().write(vals)

    @api.model
    def get_worked_day_lines(self, contracts, date_from, date_to):
        lines = []
        date_from = fields.Date.to_date(date_from)
        date_to = min(
            fields.Date.to_date(date_to), fields.Date.context_today(self))
        for contract in contracts:
            if date_from <= date_to:
                self.env['ibs.hr.attendance.day'].sudo().generate_days(
                    date_from, date_to, contract.employee_id)
            days = self.env['ibs.hr.attendance.day'].sudo().search([
                ('employee_id', '=', contract.employee_id.id),
                ('date', '>=', date_from), ('date', '<=', date_to)])
            scheduled = days.filtered(lambda day: day.scheduled_hours > 0)
            lines.append({
                'name': _('Shift Working Days'), 'sequence': 1, 'code': 'WORK100',
                'number_of_days': len(scheduled),
                'number_of_hours': sum(scheduled.mapped('scheduled_hours')),
                'contract_id': contract.id,
            })
        return lines

    def _hcm_require_role(self, role):
        if (self.env.context.get('hcm_workflow') is _HCM_WORKFLOW
                and self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_finance')):
            return
        if not self.env.su and not self.env.user.has_group('ibs_hr_payroll.ibs_hr_payroll_' + role):
            raise ValidationError(_('You are not authorized for this payroll action.'))

    hcm_source_ids = fields.One2many(
        'ibs.hr.payroll.source', 'payslip_id', readonly=True)
    hcm_overtime_ids = fields.Many2many(
        'ibs.hr.overtime', 'ibs_payslip_overtime_rel',
        'payslip_id', 'overtime_id', readonly=True)

    period_day_count = fields.Integer(
        string='Month Days', compute='_compute_hcm_period_summary')
    weekend_day_count = fields.Integer(
        string='Weekend Days', compute='_compute_hcm_period_summary')
    public_holiday_day_count = fields.Integer(
        string='Public Holidays', compute='_compute_hcm_period_summary')
    attendance_day_count = fields.Integer(
        string='Attendance Days', compute='_compute_hcm_period_summary')
    paid_leave_day_count = fields.Integer(
        string='Paid Leave Days', compute='_compute_hcm_period_summary')
    unpaid_leave_day_count = fields.Integer(
        string='Non-Paid Leave Days', compute='_compute_hcm_period_summary')
    absent_day_count = fields.Integer(
        string='Absence Days', compute='_compute_hcm_period_summary')
    lateness_minutes = fields.Integer(
        string='Lateness (Minutes)', compute='_compute_hcm_period_summary')
    overtime_hours = fields.Float(
        string='Overtime Hours', digits=(6, 2),
        compute='_compute_hcm_period_summary')

    hcm_day_record_count = fields.Integer(
        string='Day Treatments', compute='_compute_hcm_document_counts')
    hcm_fingerprint_count = fields.Integer(
        string='Fingerprints', compute='_compute_hcm_document_counts')
    hcm_holiday_count = fields.Integer(
        string='Public Holidays', compute='_compute_hcm_document_counts')
    hcm_time_off_count = fields.Integer(
        string='Time Off', compute='_compute_hcm_document_counts')
    hcm_permission_count = fields.Integer(
        string='Permissions', compute='_compute_hcm_document_counts')
    hcm_mission_count = fields.Integer(
        string='Missions', compute='_compute_hcm_document_counts')
    hcm_penalty_count = fields.Integer(
        string='Penalties', compute='_compute_hcm_document_counts')
    hcm_overtime_count = fields.Integer(
        string='Overtime', compute='_compute_hcm_document_counts')
    hcm_mobile_count = fields.Integer(
        string='Mobile Invoices', compute='_compute_hcm_document_counts')
    hcm_loan_count = fields.Integer(
        string='Loans', compute='_compute_hcm_document_counts')
    hcm_advance_count = fields.Integer(
        string='Salary Advances', compute='_compute_hcm_document_counts')

    @api.depends('employee_id', 'date_from', 'date_to')
    def _compute_hcm_period_summary(self):
        day_model = self.env['ibs.hr.attendance.day'].sudo()
        for payslip in self:
            values = {
                'period_day_count': 0,
                'weekend_day_count': 0,
                'public_holiday_day_count': 0,
                'attendance_day_count': 0,
                'paid_leave_day_count': 0,
                'unpaid_leave_day_count': 0,
                'absent_day_count': 0,
                'lateness_minutes': 0,
                'overtime_hours': 0.0,
            }
            if payslip.employee_id and payslip.date_from and payslip.date_to:
                values['period_day_count'] = (
                    payslip.date_to - payslip.date_from).days + 1
                days = day_model.search([
                    ('employee_id', '=', payslip.employee_id.id),
                    ('date', '>=', payslip.date_from),
                    ('date', '<=', payslip.date_to),
                ])
                values.update({
                    'weekend_day_count': len(days.filtered(
                        lambda day: day.state == 'weekend')),
                    'public_holiday_day_count': len(days.filtered(
                        lambda day: day.state == 'holiday')),
                    'attendance_day_count': len(days.filtered(
                        lambda day: day.worked_hours > 0)),
                    'paid_leave_day_count': len(days.filtered(
                        lambda day: day.state == 'leave' and day.is_paid_leave)),
                    'unpaid_leave_day_count': len(days.filtered(
                        lambda day: day.state == 'leave' and not day.is_paid_leave)),
                    'absent_day_count': len(days.filtered(
                        lambda day: day.state == 'absent')),
                    'lateness_minutes': sum(days.mapped('late_minutes')),
                })
                overtime_minutes = 0
                for day in days:
                    hours = (day.worked_hours
                             if day.state in ('weekend', 'holiday')
                             else day.overtime_hours)
                    minutes = math.floor(hours * 60.0 + 1e-9)
                    if minutes >= 31:
                        overtime_minutes += minutes
                values['overtime_hours'] = overtime_minutes / 60.0
            for field_name, value in values.items():
                payslip[field_name] = value

    def _hcm_document_target(self, kind):
        self.ensure_one()
        if not (self.employee_id and self.date_from and self.date_to):
            return False, []
        employee = [('employee_id', '=', self.employee_id.id)]
        dates = [('date', '>=', self.date_from), ('date', '<=', self.date_to)]
        if kind == 'fingerprint':
            day_model = self.env['ibs.hr.attendance.day']
            start = day_model._utc_datetime(self.date_from, 0.0)
            end = day_model._utc_datetime(self.date_to + timedelta(days=1), 0.0)
            return 'hr.attendance', employee + [
                ('check_in', '>=', start), ('check_in', '<', end)]
        if kind == 'time_off':
            return 'ibs.hr.time.off.request', employee + [
                ('date_from', '<=', self.date_to),
                ('date_to', '>=', self.date_from)]
        if kind in ('permission', 'mission'):
            model = ('ibs.hr.permission' if kind == 'permission'
                     else 'ibs.hr.mission')
            return model, employee + [
                ('issue_date', '>=', self.date_from),
                ('issue_date', '<=', self.date_to)]
        if kind == 'penalty':
            booked = self.penalty_deduction_ids.warning_id
            planned = self._ibs_penalty_plan()[0] if not booked else []
            warning_ids = booked.ids or [line[0].id for line in planned]
            return 'ibs.hr.warning', [('id', 'in', warning_ids)]
        if kind == 'mobile':
            return 'ibs.hr.mobile.deduction', employee + [
                ('period', '=', self._hcm_period())]
        targets = {
            'day': ('ibs.hr.attendance.day', employee + dates),
            'holiday': ('ibs.hr.public.holiday', [
                ('company_id', '=', self.employee_id.company_id.id), *dates]),
            'overtime': ('ibs.hr.overtime', employee + dates),
            'loan': ('hr.loan', employee + [
                ('loan_lines.date', '>=', self.date_from),
                ('loan_lines.date', '<=', self.date_to)]),
            'advance': ('salary.advance', employee + dates),
        }
        if kind not in targets:
            raise ValidationError(_('Unknown payroll document type.'))
        return targets[kind]

    @api.depends('employee_id', 'date_from', 'date_to', 'penalty_deduction_ids')
    @api.depends_context('uid', 'allowed_company_ids')
    def _compute_hcm_document_counts(self):
        count_fields = {
            'day': 'hcm_day_record_count',
            'fingerprint': 'hcm_fingerprint_count',
            'holiday': 'hcm_holiday_count',
            'time_off': 'hcm_time_off_count',
            'permission': 'hcm_permission_count',
            'mission': 'hcm_mission_count',
            'penalty': 'hcm_penalty_count',
            'overtime': 'hcm_overtime_count',
            'mobile': 'hcm_mobile_count',
            'loan': 'hcm_loan_count',
            'advance': 'hcm_advance_count',
        }
        for payslip in self:
            for field_name in count_fields.values():
                payslip[field_name] = 0
            if not (payslip.employee_id and payslip.date_from and payslip.date_to):
                continue
            for kind, field_name in count_fields.items():
                model_name, domain = payslip._hcm_document_target(kind)
                if model_name in self.env.registry:
                    payslip[field_name] = self.env[model_name].sudo().search_count(domain)

    def action_open_hcm_documents(self):
        self.ensure_one()
        self.check_access('read')
        kind = self.env.context.get('hcm_document_kind')
        model_name, domain = self._hcm_document_target(kind)
        if not model_name or model_name not in self.env.registry:
            raise ValidationError(_('This payroll source application is not installed.'))
        self.env[model_name].check_access('read')
        return {
            'type': 'ir.actions.act_window',
            'name': self.env[model_name]._description,
            'res_model': model_name,
            'view_mode': 'list,form',
            'domain': domain,
            'context': dict(self.env.context, create=False),
        }

    def _hcm_prepare_period_sources(self):
        today = fields.Date.context_today(self)
        for payslip in self.filtered(
                lambda item: item.employee_id and item.date_from and item.date_to):
            refresh_to = min(payslip.date_to, today)
            if payslip.date_from > refresh_to:
                continue
            self.env['ibs.hr.attendance.day'].sudo().generate_days(
                payslip.date_from, refresh_to, payslip.employee_id)
            self.env['ibs.hr.overtime'].sudo().generate_from_attendance(
                payslip.date_from, refresh_to, payslip.employee_id)

    def _hcm_period(self):
        self.ensure_one()
        return self.date_from.replace(day=1) if self.date_from else False

    def _hcm_already_consumed(self, code):
        self.ensure_one()
        if not self.employee_id or not self._hcm_period():
            return False
        return self.env['ibs.hr.payroll.source'].sudo().search_count([
            ('employee_id', '=', self.employee_id.id),
            ('period', '=', self._hcm_period()),
            ('code', '=', code),
            ('payslip_id', '!=', self.id),
        ]) > 0

    def _hcm_amounts(self):
        self.ensure_one()
        result = {code: 0.0 for code in HCM_CODES}
        contract = self.contract_id
        if not contract or not self.date_from or not self.date_to:
            return result
        days = self.env['ibs.hr.attendance.day'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
        ])
        transport_days = len(days.filtered(
            lambda day: day.worked_hours > 0 and day.state == 'present'))
        result.update({
            'TRA': transport_days * contract.transportation_allowance_daily,
            'JOB': contract.employment_allowance,
            'Comm': contract.commitment_allowance,
            'Meal': contract.other_allowance,
            'SOCIN': contract.social_insurance_amount,
        })
        overtime = self.env['ibs.hr.overtime'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
            ('state', '=', 'approved'), ('compensation', '=', 'cash'),
        ])
        result['OT100'] = sum(overtime.mapped('amount'))
        period = self._hcm_period()
        mobile = self.env['ibs.hr.mobile.deduction'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('period', '=', period), ('state', '=', 'approved'),
        ], limit=1)
        result['MOB'] = (
            mobile.amount if mobile else contract.mobile_invoice_deduction)
        daily_rate = contract.wage / 30.0
        result['ABS'] = sum(days.filtered(
            lambda day: day.state == 'absent').mapped('absence_days')) * daily_rate
        result['UNPaid'] = sum(days.filtered(
            lambda day: day.state == 'leave' and not day.is_paid_leave
        ).mapped('absence_days')) * daily_rate
        result['Late'] = sum(
            ((day.late_minutes + day.early_leave_minutes) / 60.0)
            * daily_rate / (day.scheduled_hours or 8.0)
            for day in days.filtered(lambda item: item.state == 'present'))
        result['Finger'] = len(days.filtered(
            lambda day: day.single_punch and day.scheduled_hours > 0)) * daily_rate
        for code in HCM_CODES:
            if self._hcm_already_consumed(code):
                result[code] = 0.0
        return result

    def get_inputs(self, contracts, date_from, date_to):
        self._hcm_require_role('generalist')
        contracts.check_access('read')
        date_from, date_to = fields.Date.to_date(date_from), fields.Date.to_date(date_to)
        # Payroll may consume an employee's approved financial sources
        # without granting the payroll operator access to the loan/advance apps.
        result = super(HrPayslip, self.sudo()).get_inputs(contracts, date_from, date_to)
        if len(self) != 1:
            return result
        amounts = self._hcm_amounts()
        for line in result:
            if line.get('code') in amounts:
                line['amount'] = amounts[line['code']]
        # Some deployments install the community loan bridge after payroll,
        # which makes its get_inputs override order-dependent. Resolve the due
        # installment here so the configured `Loan` rule is deterministic.
        if 'hr.loan.line' in self.env.registry:
            loan_lines = self.env['hr.loan.line'].sudo().search([
                ('employee_id', '=', self.employee_id.id),
                ('date', '>=', date_from), ('date', '<=', date_to),
                ('paid', '=', False), ('loan_id.state', '=', 'approve'),
            ])
            loan_input = next(
                (line for line in result if line.get('code') == 'Loan'), None)
            if loan_input is not None:
                loan_input['amount'] = sum(loan_lines.mapped('amount'))
                if loan_lines and 'loan_line_id' in self.env['hr.payslip.input']._fields:
                    loan_input['loan_line_id'] = loan_lines[0].id
        return result

    def _hcm_refresh_inputs(self):
        for payslip in self:
            contracts = payslip.contract_id
            if not contracts or not payslip.date_from or not payslip.date_to:
                continue
            expected = payslip.get_inputs(
                contracts, payslip.date_from, payslip.date_to)
            for values in expected:
                existing = payslip.input_line_ids.filtered(
                    lambda line: line.code == values.get('code')
                    and line.contract_id.id == values.get('contract_id'))[:1]
                if existing:
                    update = {'name': values.get('name', existing.name)}
                    if existing.code not in MANUAL_CODES:
                        update['amount'] = values.get('amount', existing.amount)
                    existing.write(update)
                else:
                    payslip.input_line_ids = [(0, 0, values)]

    def action_compute_sheet(self):
        self._hcm_require_role('generalist')
        self._hcm_prepare_period_sources()
        self._hcm_refresh_inputs()
        result = super().action_compute_sheet()
        if self.env.context.get('hcm_workflow') is not _HCM_WORKFLOW:
            self._notify_approval_group('ibs_hr_payroll.ibs_hr_payroll_finance',
                                        _('Payslip awaiting Finance confirmation'))
        return result

    def _hcm_check_sources_available(self):
        for payslip in self:
            consumed = self.env['ibs.hr.payroll.source'].sudo().search([
                ('employee_id', '=', payslip.employee_id.id),
                ('period', '=', payslip._hcm_period()),
                ('payslip_id', '!=', payslip.id),
            ])
            if consumed:
                raise ValidationError(_(
                    'Monthly HCM sources already consumed: %(codes)s',
                    codes=', '.join(sorted(set(consumed.mapped('code'))))))

    def action_payslip_done(self):
        self._hcm_require_role('finance')
        to_process = self.filtered(lambda payslip: payslip.state != 'done')
        if not to_process:
            return True
        to_process._hcm_check_sources_available()
        result = super(HrPayslip, to_process.with_context(hcm_workflow=_HCM_WORKFLOW)).action_payslip_done()
        source_model = self.env['ibs.hr.payroll.source'].sudo()
        for payslip in to_process:
            amounts = payslip._hcm_amounts()
            for code, amount in amounts.items():
                if amount:
                    source_model.create({
                        'employee_id': payslip.employee_id.id,
                        'period': payslip._hcm_period(),
                        'code': code,
                        'amount': amount,
                        'payslip_id': payslip.id,
                    })
            overtime = self.env['ibs.hr.overtime'].sudo().search([
                ('employee_id', '=', payslip.employee_id.id),
                ('date', '>=', payslip.date_from),
                ('date', '<=', payslip.date_to),
                ('state', '=', 'approved'), ('compensation', '=', 'cash'),
            ])
            overtime.write({'state': 'paid'})
            payslip.hcm_overtime_ids = overtime
            mobile = self.env['ibs.hr.mobile.deduction'].sudo().search([
                ('employee_id', '=', payslip.employee_id.id),
                ('period', '=', payslip._hcm_period()),
                ('state', '=', 'approved'),
            ], limit=1)
            mobile.write({'state': 'deducted', 'payslip_id': payslip.id})
        to_process._notify_employee(_('Payslip confirmed'))
        return result

    def _hcm_release_sources(self):
        for payslip in self:
            payslip.hcm_source_ids.sudo().unlink()
            payslip.hcm_overtime_ids.sudo().write({'state': 'approved'})
            payslip.hcm_overtime_ids = [(5, 0, 0)]
            mobile = self.env['ibs.hr.mobile.deduction'].sudo().search([
                ('payslip_id', '=', payslip.id),
            ])
            mobile.sudo().write({'state': 'approved', 'payslip_id': False})

    def action_payslip_draft(self):
        self._hcm_require_role('admin')
        self._hcm_release_sources()
        return super(HrPayslip, self.with_context(hcm_workflow=_HCM_WORKFLOW)).action_payslip_draft()

    def action_payslip_cancel(self):
        self._hcm_require_role('admin')
        self._hcm_release_sources()
        return super(HrPayslip, self.with_context(hcm_workflow=_HCM_WORKFLOW)).action_payslip_cancel()
