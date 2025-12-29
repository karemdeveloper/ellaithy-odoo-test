from odoo.addons.web.controllers.utils import ensure_db
from odoo.addons.web.controllers.action import Action
from odoo.addons.web.controllers.home import Home
from odoo.tools.translate import _
from odoo.http import request
from odoo.exceptions import UserError
from odoo import http

class Action(Action):
    
    @http.route('/web/action/run', type='json', auth="user")
    def run(self, action_id, context=None):
        res = super(Action,self).run(action_id, context)
        actions_and_prints = []
        if res:
            for access in request.env['remove.action'].search([('access_management_id.company_ids','in',request.env.company.id),('access_management_id','in',request.env.user.access_management_ids.ids),('model_id.model','=',res.get('res_model'))]):
                actions_and_prints = actions_and_prints + access.mapped('report_action_ids.action_id').ids
                actions_and_prints = actions_and_prints + access.mapped('server_action_ids.action_id').ids
                for view_data in access.view_data_ids:
                    for b_view in res['views']:
                        if b_view[1] == view_data.techname:
                            res['views'].pop(res['views'].index(b_view))
        return res
    
    @http.route('/web/action/load', type='json', auth="user")
    def load(self, action_id, additional_context=None):
        res = super(Action,self).load(action_id, additional_context=additional_context)
        if res:
            cids = request.httprequest.cookies.get('cids') and request.httprequest.cookies.get('cids').split(',')[0] or request.env.company.id
            for view_data in set(request.env['remove.action'].sudo().search([('view_data_ids','!=',False),('access_management_id.company_ids','in',int(cids)),('access_management_id','in',request.env.user.access_management_ids.ids),('model_id.model','=',res.get('res_model'))]).mapped('view_data_ids.techname')):
                for views_data_list in res.get('views'):
                    if view_data == views_data_list[1]:
                        res['views'].pop(res['views'].index(views_data_list))       
            if 'views' in res.keys() and not len(res.get('views')):
                raise UserError(_("You don't have the permission to access any views. Please contact to administrator."))
        return res
    

class Home(Home):

    @http.route(['/web', '/web/'], type='http', auth="none", sitemap=False)
    def web_client_legacy(self, s_action=None, **kw):
        """Redirect old /web URLs to /odoo for Odoo 18 compatibility"""
        # Preserve all query parameters in the redirect
        params = []
        if s_action:
            params.append(f's_action={s_action}')
        for key, value in kw.items():
            params.append(f'{key}={value}')

        redirect_url = '/odoo'
        if params:
            redirect_url += '?' + '&'.join(params)

        return request.redirect(redirect_url, code=301)

    @http.route(['/odoo', '/odoo/<path:subpath>'], type='http', auth="none")
    def web_client(self, s_action=None, subpath=None, **kw):
        ensure_db()
        # request.env['ir.ui.view'].flush_recordset()
        # request.env.flush_all()
        # request.env['ir.qweb'].clear_caches()
        # request.env['ir.actions.actions'].clear_caches()
        # request.env.registry.clear_cache()
        request.env.registry.clear_all_caches()

        user = request.env.user.browse(request.session.uid)

        # Security check: Prevent non-admin users from accessing any URLs directly
        if subpath and request.session.uid:
            is_admin = user.has_group('base.group_system') or user.has_group('base.group_erp_manager')

            if not is_admin:
                # For non-admin users, block ALL direct URL access
                # They can only navigate through menus and UI interactions
                # This prevents URL manipulation completely
                return request.redirect('/odoo')

        # if len(user.company_ids) > 1:
        #     request.env['ir.ui.menu'].clear_caches()
        if not kw.get('debug') or kw.get('debug') != "0":
            cids = request.httprequest.cookies.get('cids') and request.httprequest.cookies.get('cids').split(',')[0] or request.env.company.id
            access_management = request.env['access.management'].sudo().search([('active','=',True),('company_ids','in',int(cids)),('disable_debug_mode','=',True),('user_ids','in',user.id)],limit=1)
            if access_management.id:
                return request.redirect('/odoo?debug=0')
                # request.session.debug = '0'

        return super(Home, self).web_client(s_action=s_action, **kw)
