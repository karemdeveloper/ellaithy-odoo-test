from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _ellithy_bind_module_roles(self, module, prefix, finance=True):
        roles = {'user': 'group_ellithy_hr_user',
                 'generalist': 'group_ellithy_hr_generalist',
                 'admin': 'group_ellithy_hr_admin'}
        if finance:
            roles['finance'] = 'group_ellithy_financial_approval'
        for suffix, central in roles.items():
            group = self.env.ref('ellithy_hr_base.' + central)
            role = self.env.ref('%s.%s_%s' % (module, prefix, suffix))
            group.write({'implied_ids': [(4, role.id)]})
        return True

    @api.model
    def _ellithy_apply_hcm_roles(self):
        generalist = self.env.ref('ellithy_hr_base.group_ellithy_hr_generalist')
        finance = self.env.ref('ellithy_hr_base.group_ellithy_financial_approval')
        admin = self.env.ref('ellithy_hr_base.group_ellithy_hr_admin')
        personnel = self.env.ref('ellithy_hr_base.group_ellithy_hr_personnel')
        # Preserve existing assignments while switching policy checks to the
        # canonical role. Generalist implies the compatibility role, never
        # the reverse, so there is no cycle of implied groups.
        generalist.write({'users': [(4, user.id) for user in personnel.users]})
        admin.write({'implied_ids': [(4, generalist.id), (4, finance.id)]})
        for xmlid in ('group_ellithy_hr_personnel', 'group_ellithy_hr_assistant',
                      'group_ellithy_hr_branch_manager'):
            self.env.ref('ellithy_hr_base.' + xmlid).category_id = False
        self.env.ref('ellithy_hr_base.module_category_ellithy_hr').description = (
            'Employee self-service, HR Generalist, Financial Approval and HR Admin.')
        for xmlid in ('rule_hr_employee_all_branches', 'rule_ellithy_hr_account_hr'):
            self.env.ref('ellithy_hr_base.' + xmlid).groups = generalist
        return True
