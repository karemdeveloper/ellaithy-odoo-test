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
        return True
