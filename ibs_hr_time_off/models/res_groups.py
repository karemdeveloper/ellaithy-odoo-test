from odoo import api, models


class ResGroups(models.Model):
    _inherit = 'res.groups'

    @api.model
    def _ibs_retire_legacy_time_off(self):
        # Optional historical installation, without a dependency, model
        # inheritance or required XML reference to stock Time Off.
        root = self.env.ref('hr_holidays.menu_hr_holidays_root', raise_if_not_found=False)
        alias = self.env.ref('hr_leave_request_aliasing.mail_alias_hr_leave', raise_if_not_found=False)
        if alias:
            alias.alias_model_id = self.env['ir.model']._get('ibs.hr.time.off.request')
        if root:
            root.active = False
            access = self.env['ir.model.access'].search([
                ('model_id.model', 'in', ('hr.leave', 'hr.leave.type', 'hr.leave.allocation'))])
            access.write({'perm_write': False, 'perm_create': False, 'perm_unlink': False})
        return True
