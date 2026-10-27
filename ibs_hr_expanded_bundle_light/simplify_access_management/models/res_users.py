from odoo import fields, models, api, SUPERUSER_ID,_
from odoo.exceptions import UserError, AccessDenied
import logging
_logger = logging.getLogger(__name__)

class res_users(models.Model):
    _inherit = 'res.users'

    access_management_ids = fields.Many2many('access.management', 'access_management_users_rel_ah', 'user_id', 'access_management_id', 'Access Pack')

    # allow_ip_ids = fields.One2many('allow.ip', 'user_id', 'Allow IP')
    
    def write(self, vals):
        res = super(res_users, self).write(vals)
        for access in self.access_management_ids:
            if self.env.company in access.company_ids and access.readonly:
                if self.has_group('base.group_system') or self.has_group('base.group_erp_manager'):
                    raise UserError(_('Admin user can not be set as a read-only..!'))
        return res

    @api.model_create_multi
    def create(self, vals_list):
        res = super(res_users, self).create(vals_list)
        for record in self:
            for access in record.access_management_ids:    
                if self.env.company in access.company_ids and access.readonly:
                    if record.has_group('base.group_system') or record.has_group('base.group_erp_manager'):
                        raise UserError(_('Admin user can not be set as a read-only..!'))
        return res


    @classmethod
    def _login(cls, db, credential, user_agent_env=None):
        auth_info = super(res_users, cls)._login(db, credential, user_agent_env=user_agent_env)
        try:
            # Extract user_id from auth_info dictionary
            user_id = auth_info.get('uid') if isinstance(auth_info, dict) else auth_info

            with cls.pool.cursor() as cr:
                self = api.Environment(cr, SUPERUSER_ID, {})[cls._name]
                access_management_obj = self.env['access.management']

                if access_management_obj.search([('user_ids', 'in', [user_id]), ('disable_login', '=', True)]):
                    raise AccessDenied()
        except AccessDenied:
            login = credential.get('login', 'unknown') if isinstance(credential, dict) else 'unknown'
            _logger.info("Login failed for db:%s login:%s", db, login)
            raise
        return auth_info
        