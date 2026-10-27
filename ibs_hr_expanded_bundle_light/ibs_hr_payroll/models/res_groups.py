from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _hcm_apply_payroll_security(self):
        finance = self.env.ref('ibs_hr_payroll.ibs_hr_payroll_finance')
        accountant = self.env.ref('account.group_account_user', raise_if_not_found=False)
        if accountant:
            finance.write({'implied_ids': [(4, accountant.id)]})
        config_models = ('hr.salary.rule', 'hr.payroll.structure',
                         'hr.salary.rule.category', 'hr.contribution.register',
                         'hr.rule.input', 'hr.contract.advantage.template')
        officer = self.env.ref('hr_payroll_community.group_hr_payroll_community_user')
        access = self.env['ir.model.access'].search([
            ('model_id.model', 'in', config_models), ('group_id', '=', officer.id)])
        access.write({'perm_write': False, 'perm_create': False, 'perm_unlink': False})
        # Replaced by the configured workbook rules.  Keep the vendor rows
        # for audit, but prevent duplicate codes and duplicate amounts.
        for xmlid in (
                'hr_payroll_community.hr_rule_da',
                'hr_payroll_community.hr_rule_hra',
                'hr_payroll_community.hr_rule_travel',
                'hr_payroll_community.hr_rule_meal',
                'hr_payroll_community.hr_rule_medical',
                'hr_payroll_community.hr_rule_other',
                'employee_bonus_manager.hr_salary_rule_bonus',
                'ohrms_overtime.hr_salary_rule_overtime',
                'ohrms_salary_advance.hr_payslip_rule_advance'):
            rule = self.env.ref(xmlid, raise_if_not_found=False)
            if rule:
                rule.active = False
        old_codes = {
            'TRANSPORT': 'TRA', 'EMPLOYMENT': 'JOB',
            'COMMITMENT': 'Comm', 'OTHER_ALLOW': 'Meal',
            'OVERTIME': 'OT100', 'SOC_INS': 'SOCIN',
            'MOBILE': 'MOB', 'UNPAID_TIME': 'ABS',
        }
        sources = self.env['ibs.hr.payroll.source'].sudo().search([
            ('code', 'in', list(old_codes))])
        for source in sources:
            new_code = old_codes[source.code]
            duplicate = self.env['ibs.hr.payroll.source'].sudo().search_count([
                ('id', '!=', source.id),
                ('employee_id', '=', source.employee_id.id),
                ('period', '=', source.period),
                ('code', '=', new_code),
            ])
            # Preserve an old audit row if a new-code row already exists for
            # the same employee and month; the SQL constraint forbids merging.
            source.code = ('LEGACY_%s_%s' % (source.code, source.id)
                           if duplicate else new_code)

        # These vendor records were originally loaded with noupdate="1", so
        # normal XML upgrades cannot change their formulas or sequences.
        forced_rules = {
            'hr_payroll_community.hr_rule_basic': {
                'name': 'Basic Salary', 'code': 'BASIC', 'sequence': 100,
                'condition_select': 'none', 'amount_select': 'code',
                'amount_python_compute': 'result = contract.wage',
            },
            'hr_payroll_community.hr_rule_taxable': {
                'name': 'Gross', 'code': 'GROSS', 'sequence': 300,
                'condition_select': 'none', 'amount_select': 'code',
                'amount_python_compute': 'result = categories.BASIC + categories.ALW',
            },
            'ibs_hr.hr_salary_rule_penalty': {
                'name': 'Penalty', 'code': 'PENALTY', 'sequence': 600,
                'condition_select': 'none', 'amount_select': 'code',
                'amount_python_compute': 'result = -inputs.PENALTY.amount',
            },
            'hr_payroll_community.hr_rule_net': {
                'name': 'Net Salary', 'code': 'NET', 'sequence': 700,
                'condition_select': 'none', 'amount_select': 'code',
                'amount_python_compute': (
                    'result = categories.BASIC + categories.ALW + categories.DED'),
            },
        }
        for xmlid, values in forced_rules.items():
            rule = self.env.ref(xmlid, raise_if_not_found=False)
            if rule:
                rule.write(values)
        structure = self.env.ref('hr_payroll_community.structure_base')
        configured = self.env['hr.salary.rule']
        for xmlid in (
                'ibs_hr_payroll.rule_employment',
                'ibs_hr_payroll.rule_transport',
                'ibs_hr_payroll.rule_commitment',
                'ibs_hr_payroll.rule_other_allow',
                'ibs_hr_payroll.rule_kpi', 'ibs_hr_payroll.rule_bonus',
                'ibs_hr_payroll.rule_overtime', 'ibs_hr_payroll.rule_mobile',
                'ibs_hr_payroll.rule_social_insurance',
                'ibs_hr_payroll.rule_medical_insurance',
                'ibs_hr.hr_salary_rule_penalty',
                'ibs_hr_payroll.rule_advance', 'ibs_hr_payroll.rule_absence',
                'ibs_hr_payroll.rule_lateness',
                'ibs_hr_payroll.rule_fingerprint',
                'ibs_hr_payroll.rule_unpaid_time', 'ibs_hr_payroll.rule_loan',
                'ibs_hr_payroll.rule_hiring_adjustment',
                'ibs_hr_payroll.rule_resignation_adjustment'):
            rule = self.env.ref(xmlid, raise_if_not_found=False)
            if rule:
                configured |= rule
        if configured:
            structure.write({'rule_ids': [(4, rule.id) for rule in configured]})
        return True
