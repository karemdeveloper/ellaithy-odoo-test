from odoo.addons.web.controllers.utils import ensure_db
from odoo.addons.web.controllers.action import Action
from odoo.addons.web.controllers.home import Home
from odoo.tools.translate import _
from odoo.http import request
from odoo.exceptions import UserError
from odoo import http
import logging

_logger = logging.getLogger(__name__)

class Action(Action):

    @http.route('/web/action/run', type='json', auth="user")
    def run(self, action_id, context=None):
        res = super(Action,self).run(action_id, context)

        # Track legitimate action access in session
        if action_id and request.session.uid:
            if 'accessed_actions' not in request.session:
                request.session['accessed_actions'] = []

            accessed = request.session['accessed_actions']
            if action_id not in accessed:
                accessed.append(action_id)
                # Explicitly set back to trigger session modification
                request.session['accessed_actions'] = accessed
                request.session.modified = True
                _logger.info(f"Action Tracking (run) - Added action {action_id} to session. Current list: {accessed}")

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

        # Track legitimate action access in session
        if action_id and request.session.uid:
            if 'accessed_actions' not in request.session:
                request.session['accessed_actions'] = []

            accessed = request.session['accessed_actions']
            if action_id not in accessed:
                accessed.append(action_id)
                # Explicitly set back to trigger session modification
                request.session['accessed_actions'] = accessed
                request.session.modified = True
                _logger.info(f"Action Tracking (load) - Added action {action_id} to session. Current list: {accessed}")

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
        request.env.registry.clear_all_caches()

        _logger.info(f"web_client called - subpath: {subpath}, session.uid: {request.session.get('uid')}")

        # Security check for non-admin users BEFORE loading the page
        # Check if user is authenticated by looking at session cookie
        if subpath and request.session.get('uid'):
            uid = request.session.get('uid')
            _logger.info(f"User authenticated - uid: {uid}, checking subpath: {subpath}")
            # Get user from current environment
            user = request.env['res.users'].sudo().browse(uid)
            is_admin = user.has_group('base.group_system') or user.has_group('base.group_erp_manager')
            _logger.info(f"User: {user.login}, is_admin: {is_admin}")

            if not is_admin:
                # Extract action ID from URL (e.g., "action-429" -> 429)
                if subpath.startswith('action-'):
                    try:
                        action_id = int(subpath.split('-')[1].split('/')[0])
                        _logger.info(f"Extracted action_id: {action_id}")

                        # Menu-based security check: Verify user has access to a menu that uses this action
                        # Get all visible menu IDs for the current user (using sudo to bypass access checks in auth="none" context)
                        _logger.info(f"Getting visible menu IDs for uid {uid}...")
                        visible_menu_ids = request.env['ir.ui.menu'].sudo()._visible_menu_ids(uid)
                        _logger.info(f"Visible menu IDs: {visible_menu_ids[:10] if len(visible_menu_ids) > 10 else visible_menu_ids}... (total: {len(visible_menu_ids)})")

                        # Check if any visible menu links to this action
                        accessible_menus = request.env['ir.ui.menu'].sudo().search([
                            ('id', 'in', visible_menu_ids),
                            '|',
                            ('action', '=', f'ir.actions.act_window,{action_id}'),
                            ('action', '=', f'ir.actions.server,{action_id}')
                        ])

                        _logger.info(f"URL Security Check - Action ID: {action_id}, User: {user.login}, Has Menu Access: {bool(accessible_menus)}, Accessible menus: {accessible_menus.ids}")

                        if not accessible_menus:
                            # User doesn't have any menu that links to this action
                            # Redirect to home
                            _logger.warning(f"Access denied - User {user.login} tried to access action {action_id} without menu permission")
                            return request.redirect('/odoo')

                    except (ValueError, IndexError) as e:
                        # Invalid action format, redirect to home
                        _logger.error(f"ValueError/IndexError parsing action: {e}")
                        return request.redirect('/odoo')
                    except Exception as e:
                        # Log any other exceptions
                        _logger.error(f"Unexpected error in URL security check: {e}", exc_info=True)
                        return request.redirect('/odoo')
                elif not subpath.startswith('res.partner/'):
                    # For non-admin users, block all other direct URL access
                    # (settings, models, records, etc.)
                    # Only allow res.partner record URLs for the "Open Existing Customer" button
                    return request.redirect('/odoo')

        # Debug mode check
        if not kw.get('debug') or kw.get('debug') != "0":
            cids = request.httprequest.cookies.get('cids') and request.httprequest.cookies.get('cids').split(',')[0] or request.env.company.id
            if request.session.get('uid'):
                uid = request.session.get('uid')
                user = request.env['res.users'].sudo().browse(uid)
                access_management = request.env['access.management'].sudo().search([('active','=',True),('company_ids','in',int(cids)),('disable_debug_mode','=',True),('user_ids','in',user.id)],limit=1)
                if access_management.id:
                    return request.redirect('/odoo?debug=0')

        return super(Home, self).web_client(s_action=s_action, **kw)
