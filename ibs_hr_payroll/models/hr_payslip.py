from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


HCM_CODES = (
    'TRANSPORT', 'EMPLOYMENT', 'COMMITMENT', 'OTHER_ALLOW',
    'OVERTIME', 'SOC_INS', 'MOBILE', 'UNPAID_TIME',
)


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
        for contract in contracts:
            self.env['ibs.hr.attendance.day'].sudo().generate_days(
                fields.Date.to_date(date_from), fields.Date.to_date(date_to), contract.employee_id)
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
            'TRANSPORT': (transport_days
                          * contract.transportation_allowance_daily),
            'EMPLOYMENT': contract.employment_allowance,
            'COMMITMENT': contract.commitment_allowance,
            'OTHER_ALLOW': contract.other_allowance,
            'SOC_INS': contract.social_insurance_amount,
        })
        overtime = self.env['ibs.hr.overtime'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('date', '>=', self.date_from), ('date', '<=', self.date_to),
            ('state', '=', 'approved'), ('compensation', '=', 'cash'),
        ])
        result['OVERTIME'] = sum(overtime.mapped('amount'))
        period = self._hcm_period()
        mobile = self.env['ibs.hr.mobile.deduction'].sudo().search([
            ('employee_id', '=', self.employee_id.id),
            ('period', '=', period), ('state', '=', 'approved'),
        ], limit=1)
        result['MOBILE'] = (
            mobile.amount if mobile else contract.mobile_invoice_deduction)
        daily_rate = contract.wage / 30.0
        unpaid_days = sum(days.filtered(
            lambda day: day.state == 'absent' or (
                day.state == 'leave' and not day.is_paid_leave)
        ).mapped('absence_days'))
        shortfall_amount = sum(
            (day.shortfall_hours
             * daily_rate / (day.scheduled_hours or 8.0))
            for day in days.filtered(
                lambda item: item.state == 'present' and item.shortfall_hours))
        result['UNPAID_TIME'] = unpaid_days * daily_rate + shortfall_amount
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
                    existing.write({
                        'amount': values.get('amount', existing.amount),
                        'name': values.get('name', existing.name),
                    })
                else:
                    payslip.input_line_ids = [(0, 0, values)]

    def action_compute_sheet(self):
        self._hcm_require_role('generalist')
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
