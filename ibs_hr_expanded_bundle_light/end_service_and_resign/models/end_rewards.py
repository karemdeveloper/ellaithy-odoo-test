import calendar
from datetime import date
from email.policy import default
from dateutil.relativedelta import relativedelta
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

from odoo import api, fields, models, _


class EndRewards(models.Model):
    _name = 'end.rewards'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "End Rewards"
    _rec_name = "employee_id"

    employee_id = fields.Many2one('hr.employee', 'Employee', store=True)
    department_id = fields.Many2one(comodel_name="hr.department", string="Department",
                                    related='employee_id.department_id', store=True)
    location_id = fields.Many2one(comodel_name="hr.work.location", string="Work location",
                                  related='employee_id.work_location_id', store=True)
    country_id = fields.Many2one(comodel_name="res.country", string="Nationality", related='employee_id.country_id',
                                 store=True)

    contract_id = fields.Many2one('hr.contract', string="Contract", related='employee_id.contract_id', readonly=True,
                                  store=True)
    con_year_id = fields.Selection(related='contract_id.year_contract', store=True, string="Contract Year")
    wage = fields.Float(string="Basic Wage", store=True)
    hiring_date = fields.Date(string="Hiring Date", store=True)
    payslip_date = fields.Date(string="This month's payslip date", store=True)

    end_date = fields.Date(string="Current Date", default=fields.Date.today)
    payslip_id = fields.Many2one('hr.payslip', string="Payslip", readonly=True, store=True)
    gross = fields.Float(string="Total salary", store=True)
    allowances = fields.Float(string="Allowances", compute="_compute_allowances", store=True)
    working_days = fields.Float(string='Working days', default=30, readonly=True, store=True)

    days_in_month = fields.Float(string="Working days during this month", compute="_compute_days_in_month", store=True)
    daily = fields.Float(string='Worker daily', compute="_compute_daily", store=True)
    salary_due = fields.Float(string="Total salary due", compute="_compute_salary_due", store=True, readonly=False)
    actual_days = fields.Integer(string="Number of actual working days", compute="_compute_days_between", store=True)
    value = fields.Float(string="Annual value due daily", compute="_compute_value", store=True)

    allocation_id = fields.Many2one('hr.leave.allocation', string="Allocation", readonly=True)
    vacation_days = fields.Char(string="Total number of vacation days due", compute="_compute_vacation", store=True)
    vacation_day = fields.Char(string="Total number of vacation days due", compute="_compute_vacation_end", store=True)
    leave_allowance = fields.Float(string="Leave allowance", compute="_compute_leave", store=True, readonly=False)
    leave_allowance_total = fields.Float(string="Leave allowance Total")
    total_end = fields.Float(string="Total End  Service Reward ")
    leave_allowance_end = fields.Float(string="Leave allowance", compute="_compute_leave_end", store=True,
                                       readonly=False)
    service_gratuity = fields.Float(string="Total of service gratuity", compute='_compute_service_gratuity', store=True,
                                    readonly=False)
    total_rewords = fields.Float(compute="_compute_total", readonly=False, store=True)

    type_resignation = fields.Selection([
        ('end_of_service', 'نهاية خدمة '),
        ('resignation', ' استقالة'),
        ('violation', 'نهاية الخدمه ماده 80'),
        ('other', 'Other')

    ], string='Type service gratuity ', default='end_of_service')

    type_violation = fields.Selection([
        ('assault', 'التعدي على زميل أو مدير'),
        ('unethical_behavior', 'فعل مناف للأخلاق أو يخل بالشرف والآمانة'),
        ('contract_breach', 'عدم الالتزام ببنود عقد العمل'),
        ('absenteeism', 'غياب أكثر من 20 يوم بدون عذر'),
        ('intentional_loss', 'التسبب في خسائر مقصودة للشركة'),
        ('sabotage', 'القيام بأعمال تخريبية في العمل'),
        ('less_than_two_years', 'عدم إكمال عامين في الوظيفة'),
        ('other', 'Other')
    ], string='Type Violation')

    amount = fields.Float(string='Amount of grant')
    amount2 = fields.Float(string='Amount of grant')
    amount_ded = fields.Float(string='Deduction ')
    reason_grant = fields.Many2many('type.amount', string='Reason Deduction')
    reason_grant1 = fields.Many2many('type.amount1', string='Reason grant')
    reason_grant2 = fields.Many2many('type.amount2', string='Reason grant')

    total = fields.Float(string='Total Salary due')

    @api.onchange('employee_id', 'service_gratuity', 'leave_allowance_total', 'gross')
    def final_total(self):
        for line in self:
            line.total = line.salary_due

    # date_from = fields.Date('Date From')
    # date_to = fields.Date('Date To')
    leave_ids = fields.Many2many('hr.leave', string='Leave Employee',
                                 domain="[('holiday_status_id.name', 'ilike', 'Annual Leaves')]")

    # leave_ids_domain = fields.Char(compute="_compute_leave_domain" , store=True)
    #
    # @api.depends('employee_id')
    # def _compute_leave_domain(self):
    #     for rec in self:
    #         if rec.employee_id:
    #             rec.leave_ids_domain = str([('employee_id.id', 'in', rec.employee_id.id)])
    #             print(rec.leave_ids_domain)
    #         else:
    #             rec.leave_ids_domain = '[]'

    # @api.onchange('leave_allowance_end','type_resignation','employee_id')
    # def toto_end_onchage(self):
    #     for line in self:
    #         line.total_end = line.service_gratuity + line.leave_allowance_end

    @api.onchange('leave_allowance', 'employee_id', 'type_resignation')
    def store_allowance(self):
        for line in self:
            line.leave_allowance_total = line.leave_allowance

    @api.depends('gross', 'wage')
    def _compute_allowances(self):
        for record in self:
            if record.gross != 0:
                record.allowances = record.gross - record.wage
            else:
                record.allowances = 0.0

    @api.onchange('employee_id')
    def _onchange_employee_contract(self):
        if self.employee_id:
            contract = self.env['hr.contract'].search(
                [('employee_id', '=', self.employee_id.id), ('state', '=', 'open')], limit=1)
            if contract:
                self.wage = contract.wage
            else:
                self.wage = 0.0

    @api.onchange('employee_id')
    def _onchange_employee_date(self):
        if self.employee_id:
            contract = self.env['hr.contract'].search(
                [('employee_id', '=', self.employee_id.id), ('state', '=', 'open')], limit=1)
            if contract:
                self.contract_id = contract.id
                self.hiring_date = contract.date_start
            else:
                self.contract_id = False
                self.hiring_date = False

    # @api.onchange('employee_id')
    # def _onchange_employee_gross(self):
    #     if self.employee_id:
    #         payslip = self.env['hr.payslip'].search([('employee_id', '=', self.employee_id.id)], limit=1)
    #
    #         if payslip:
    #             self.payslip_date = payslip.date_from
    #             ts_line = payslip.line_ids.filtered(lambda line: line.code == 'TS')
    #             if ts_line:
    #                 self.gross = ts_line.amount
    #             else:
    #                 self.gross = 0.0
    #         else:
    #             self.payslip_date = False
    #             self.gross = 0.0

    @api.onchange('employee_id')
    def _onchange_employee_gross(self):
        # Gross = BASIC + ALW, matching the default hr_payroll_community
        # salary rules (GROSS = categories.BASIC + categories.ALW), where
        # ALW is the sum of the standard contract allowance fields below.
        # There are no contract-level deduction fields in hr_payroll_community
        # (deductions live on the payslip), so none are subtracted here.
        if self.employee_id:
            contract = self.env['hr.contract'].search([('employee_id', '=', self.employee_id.id)], limit=1)

            if contract:
                self.gross = (contract.wage + contract.hra + contract.da + contract.travel_allowance
                              + contract.meal_allowance + contract.medical_allowance + contract.other_allowance)
            else:
                self.gross = 0.0

    # @api.onchange('amount')
    # def _onchange_amount(self):
    #     if self.amount:
    #         self.total_rewords += self.amount

    @api.depends('gross')
    def _compute_daily(self):
        for line in self:
            line.daily = line.gross / line.working_days if line.working_days else 0.0

    @api.depends('daily', 'days_in_month')
    def _compute_salary_due(self):
        for line in self:
            line.salary_due = line.daily * line.days_in_month

    @api.depends('hiring_date', 'end_date')
    def _compute_days_between(self):
        for record in self:
            # 365
            # if record.hiring_date and record.end_date:
            #     hiring_date = fields.Date.from_string(record.hiring_date)
            #     end_date = fields.Date.from_string(record.end_date)
            #     difference = end_date - hiring_date
            #     record.actual_days = difference.days
            # else:
            #     record.actual_days = 0

            # 360
            if record.hiring_date and record.end_date:
                # تحويل التواريخ إلى كائنات datetime.date
                hiring_date = fields.Date.from_string(record.hiring_date)
                end_date = fields.Date.from_string(record.end_date)

                # حساب الفرق في السنوات والأشهر والأيام
                delta = relativedelta(end_date, hiring_date)

                # حساب إجمالي الأيام بناءً على سنة 360 يومًا
                total_days = (delta.years * 360) + (delta.months * 30) + delta.days
                record.actual_days = total_days
            else:
                record.actual_days = 0

    @api.depends('actual_days')
    def _compute_value(self):
        for line in self:
            line.value = 30 / 360 if line.actual_days >= 5 * 360 else 21 / 360

    @api.depends('leave_ids')
    def _compute_vacation(self):
        for record in self:
            total_days = 0.0
            for leave in record.leave_ids:
                try:
                    total_days += float(leave.duration_display.split()[0])
                except (ValueError, TypeError):
                    continue
            record.vacation_days = total_days

    # @api.depends('employee_id', 'date_from', 'date_to')
    # def _compute_vacation(self):
    #     for record in self:
    #         if record.employee_id and record.date_from and record.date_to:
    #
    #             # Total used during that period
    #             used_leaves = self.env['hr.leave'].search([
    #                 ('employee_id', '=', record.employee_id.id),
    #                 ('state', '=', 'validate'),
    #                 ('date_from', '<=', record.date_to),
    #                 ('date_to', '>=', record.date_from),
    #             ])
    #             used_days = sum(leave.number_of_days for leave in used_leaves)
    #
    #             record.vacation_days = used_days
    #         else:
    #             record.vacation_days = 0.0

    @api.depends("employee_id")
    def _compute_vacation_end(self):
        for record in self:
            if record.employee_id:
                record.vacation_day = record.employee_id.allocation_remaining_display
            else:
                record.vacation_day = 0

    @api.depends("vacation_day", "daily")
    def _compute_leave(self):
        for line in self:
            if line.daily and line.vacation_day:
                vac_f = float(line.vacation_day.split()[0])
                vacf = line.daily * vac_f
                line.leave_allowance = vacf

            else:
                line.leave_allowance = 0.0

    @api.depends("vacation_days", "daily")
    def _compute_leave_end(self):
        for line in self:
            if line.daily and line.vacation_days:
                vac_e = float(line.vacation_days.split()[0])
                vace = line.daily * vac_e
                line.leave_allowance_end = vace

            else:
                line.leave_allowance_end = 0.0

    @api.depends('end_date')
    def _compute_days_in_month(self):
        for record in self:
            if record.end_date:
                year = record.end_date.year
                month = record.end_date.month
                last_day_of_month = calendar.monthrange(year, month)[1]
                last_date_of_month = date(year, month, last_day_of_month)
                days_remaining = (last_date_of_month - record.end_date).days
                record.days_in_month = last_day_of_month - days_remaining
            else:
                record.days_in_month = 0

    #     this function calculate the end of service gratuity
    @api.depends('actual_days', 'gross', 'type_resignation', 'amount', 'amount2', 'amount_ded', 'leave_allowance',
                 'leave_allowance_total')
    def _compute_service_gratuity(self):
        resu = 0
        for line in self:
            if line.type_resignation == 'end_of_service':
                if line.actual_days and line.gross:
                    years_of_service = line.actual_days / 360
                    if years_of_service < 5:
                        # من سنتين إلى أقل من خمس سنوات: ثلث المكافأة
                        resu = (line.gross * 0.5 * years_of_service) + line.amount + line.amount2 - line.amount_ded
                    elif 5 <= years_of_service < 10:
                        # من خمس سنوات إلى أقل من عشر سنوات: ثلثي المكافأة
                        first_five_years = (line.gross * 0.5 * 5)  # نصف شهر عن كل سنة للسنوات الخمس الأولى
                        remaining_years = years_of_service - 5
                        after_five_years = (line.gross * 1.0 * remaining_years)  # شهر كامل عن كل سنة بعد الخمس سنوات
                        resu = (first_five_years + after_five_years) + line.amount + line.amount2 - line.amount_ded
                    else:
                        # عشر سنوات أو أكثر: مكافأة كاملة
                        first_five_years = (line.gross * 0.5 * 5)  # نصف شهر عن كل سنة للسنوات الخمس الأولى
                        remaining_years = years_of_service - 5
                        after_five_years = (line.gross * 1.0 * remaining_years)  # شهر كامل عن كل سنة بعد الخمس سنوات
                        resu = first_five_years + after_five_years + line.amount + line.amount2 - line.amount_ded
                else:
                    resu = 0
            elif line.type_resignation == 'resignation':
                if line.actual_days and line.gross:
                    years_of_service = line.actual_days / 360

                    if years_of_service < 2:
                        # أقل من سنتين: لا يستحق مكافأة
                        resu = 0.0 + line.amount + line.amount2 - line.amount_ded
                    elif 2 <= years_of_service < 5:
                        # من سنتين إلى أقل من خمس سنوات: ثلث المكافأة
                        resu = ((
                                            line.gross * 0.5 * years_of_service) / 3) + line.amount + line.amount2 - line.amount_ded
                    elif 5 <= years_of_service < 10:
                        # من خمس سنوات إلى أقل من عشر سنوات: ثلثي المكافأة
                        first_five_years = (line.gross * 0.5 * 5)  # نصف شهر عن كل سنة للسنوات الخمس الأولى
                        remaining_years = years_of_service - 5
                        after_five_years = (line.gross * 1.0 * remaining_years)  # شهر كامل عن كل سنة بعد الخمس سنوات
                        resu = ((first_five_years + after_five_years) * (
                                2 / 3)) + line.amount + line.amount2 - line.amount_ded
                    else:
                        # عشر سنوات أو أكثر: مكافأة كاملة
                        first_five_years = (line.gross * 0.5 * 5)  # نصف شهر عن كل سنة للسنوات الخمس الأولى
                        remaining_years = years_of_service - 5
                        after_five_years = (line.gross * 1.0 * remaining_years)  # شهر كامل عن كل سنة بعد الخمس سنوات
                        resu = ((first_five_years + after_five_years) * (
                                2 / 3)) + line.amount + line.amount2 - line.amount_ded
            else:
                # في حالة المخالفة: لا يستحق مكافأة
                resu = 0.0 + line.amount + line.amount2 - line.amount_ded
        self.service_gratuity = resu
        self.total_end = self.service_gratuity + self.leave_allowance_total + self.total

    @api.depends('salary_due', 'leave_allowance', 'amount', 'amount2', 'amount_ded', 'leave_allowance_end')
    def _compute_total(self):
        for line in self:
            if line.salary_due or line.leave_allowance or line.leave_allowance_end:
                self.total_rewords = line.salary_due + line.amount + line.amount2 - line.amount_ded + line.leave_allowance_end
            else:
                self.total_rewords = 0.0

    state = fields.Selection(string="State", tracking=True,
                             selection=[('draft', 'Draft'),
                                        ('confirmed', 'Confirmed'),
                                        ('cancel', 'Cancelled')],
                             default='draft', copy=False)
    account_move_id = fields.Many2one('account.journal', 'Salary Journal', readonly=True, required=False,
                                      default=lambda self: self.env['account.journal'].search(
                                          [('name', '=', 'End_Service')], limit=1))
    move_id = fields.Many2one('account.move', readonly=True)
    account_debit_id = fields.Many2one('account.account', string='Account to Debit')
    account_credit_id = fields.Many2one('account.account', string='Account to Credit')

    def _create_account_move_for_gratuity(self):
        for record in self:
            if record.state == 'confirmed' and record.service_gratuity > 0:
                # Ensure both debit and credit accounts are configured
                account_debit = record.account_debit_id
                account_credit = record.account_credit_id

                if not account_debit or not account_credit:
                    raise UserError("Please configure both debit and credit accounts for the selected grant type.")

                # Log debug messages for the account IDs
                _logger.info("Debit Account: %s, Credit Account: %s", account_debit.name, account_credit.name)

                # Find the journal with the name 'End_Service'
                journal = self.env['account.journal'].search([('name', '=', 'End_Service')], limit=1)

                if not journal:
                    raise UserError("The journal 'End_Service' does not exist. Please create it first.")

                # Create journal entry
                move_vals = {
                    'journal_id': journal.id,  # Use the 'End_Service' journal
                    'date': fields.Date.today(),
                    'ref': f'Service Gratuity for {record.employee_id.name}',
                    'line_ids': [
                        (0, 0, {
                            'name': f'Service Gratuity for {record.employee_id.name}',
                            'account_id': account_debit.id,
                            'debit': record.service_gratuity,
                            'credit': 0.0,
                            'partner_id': record.employee_id.address_home_id.id,  # Assuming partner is the employee
                        }),
                        (0, 0, {
                            'name': f'Service Gratuity for {record.employee_id.name}',
                            'account_id': account_credit.id,
                            'debit': 0.0,
                            'credit': record.service_gratuity,
                            'partner_id': record.employee_id.address_home_id.id,  # Assuming partner is the employee
                        }),
                    ]
                }

                # Creating the journal entry
                try:
                    move = self.env['account.move'].create(move_vals)

                    # Ensure the move is not already posted before calling the post method
                    if move.state == 'confirmed':
                        move.post()

                    # Log successful creation
                    _logger.info("Journal entry created and posted successfully: %s", move.id)

                    # Store the created move in the record
                    record.move_id = move.id

                except Exception as e:
                    _logger.error("Error creating or posting journal entry: %s", str(e))
                    raise UserError(f"Failed to create journal entry: {str(e)}")

    def action_confirm(self):
        for record in self:
            if record.state == 'draft':
                record.state = 'confirmed'
                # Call the method to create the account move after confirmation
                record._create_account_move_for_gratuity()

    def action_draft(self):
        for record in self:
            if record.state == 'cancel':
                record.state = 'draft'

    def action_cancel(self):
        for record in self:
            if record.state == 'confirmed' or record.state == 'draft':
                record.state = 'cancel'
                # إزالة حركة الحساب إذا كانت موجودة
                if record.move_id:
                    try:
                        # حذف حركة الحساب المرتبطة
                        record.move_id.unlink()  # حذف الحركة
                        record.move_id = False  # مسح المرجع لحركة الحساب
                        _logger.info("تم حذف حركة الحساب بنجاح: %s", record.move_id.id)
                    except Exception as e:
                        _logger.error("حدث خطأ أثناء حذف حركة الحساب: %s", str(e))
                        raise UserError(f"فشل في حذف حركة الحساب: {str(e)}")
                else:
                    _logger.info("لا توجد حركة حساب لحذفها.")


class TypeAmount(models.Model):
    _name = 'type.amount'

    name = fields.Char(string='Type of allowance')


class TypeAmount1(models.Model):
    _name = 'type.amount2'

    name = fields.Char(string='Type of allowance')


class TypeAmount2(models.Model):
    _name = 'type.amount1'

    name = fields.Char(string='Type of allowance')


class HrLeave(models.Model):
    _inherit = 'hr.leave'

    def _compute_display_name(self):
        for leave in self:
            name = leave.employee_id.name or ''
            if leave.holiday_status_id:
                name += f' - {leave.holiday_status_id.name}'
            leave.display_name = name

    @api.model
    def _search_display_name(self, operator, value):
        domain = []
        if value:
            # ابحث أولاً باسم الموظف
            domain = ['|', ('employee_id.name', operator, value), ('name', operator, value)]
        return domain
