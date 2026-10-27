from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _ibs_apply_penalty_roles(self):
        approver = self.env.ref('ibs_hr.group_ibs_admin_penalty_approver')
        generalist = self.env.ref('ibs_hr.penalty_generalist')
        admin = self.env.ref('ibs_hr.penalty_admin')
        approver.implied_ids = generalist
        admin.write({'implied_ids': [(4, approver.id)]})
        self.env.ref('ibs_hr.rule_warning_hr').write({
            'groups': [(6, 0, generalist.ids)],
            'domain_force': "[('employee_id.company_id', 'in', company_ids)]"})
        return True
