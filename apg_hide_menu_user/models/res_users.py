# -*- coding: utf-8 -*-

from odoo import fields, models


class ResUsers(models.Model):
    """
    Model to handle hiding specific menu items for certain users.
    """
    _inherit = 'res.users'


    production_department_id = fields.Char()
    def write(self, vals):
        """
         Write method for the ResUsers model.
         Ensure the menu will not remain hidden after removing it from the list.
           """
        res = super(ResUsers, self).write(vals)
        for record in self:
            for menu in record.hide_menu_ids:
                menu.write({
                    'restrict_user_ids': [fields.Command.link(record.id)]
                })
            # Handle unlinked menus (removed from hide_menu_ids)
            previous_menus = self.env['ir.ui.menu'].search(
                [('restrict_user_ids', 'in', [record.id])])
            removed_menus = previous_menus - record.hide_menu_ids
            for menu in removed_menus:
                menu.write({
                    'restrict_user_ids': [fields.Command.unlink(record.id)]
                })
        return res

    def _get_is_admin(self):
        """
        Compute method to check if the user is an admin.
        The Hide specific menu tab will be hidden for the Admin user form.
        """
        for rec in self:
            rec.is_admin = False
            if rec.id == self.env.ref('base.user_admin').id:
                rec.is_admin = True

    hide_menu_ids = fields.Many2many(
        'ir.ui.menu', string="Hidden Menu",
        store=True, help='Select menu items that need to '
                         'be hidden to this user.')
    is_admin = fields.Boolean(compute=_get_is_admin, string="Is Admin",
                              help='Check if the user is an admin.')



class IrUiMenu(models.Model):
    """
    Model to restrict the menu for specific users.
    """
    _inherit = 'ir.ui.menu'

    restrict_user_ids = fields.Many2many(
        'res.users', string="Restricted Users",
        help='Users restricted from accessing this menu.')
