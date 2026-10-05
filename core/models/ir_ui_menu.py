from odoo import models, api


class IrUiMenu(models.Model):
    _inherit = 'ir.ui.menu'

    def _is_super_admin(self):
        user = self.env.user
        return bool(
            self.env.su
            or user.id == 1
            or getattr(user, 'havano_role', None) == 'super_admin'
            or user.has_group('base.group_system')
        )

    def _load_menus_blacklist(self):
        res = super()._load_menus_blacklist()
        if self._is_super_admin():
            menu_my_sub = self.env.ref('havanoposdesk_odoo.menu_my_subscription', raise_if_not_found=False)
            if menu_my_sub:
                if isinstance(res, (list, tuple, set)):
                    res = list(res)
                    if menu_my_sub.id not in res:
                        res.append(menu_my_sub.id)
                else:
                    res = [menu_my_sub.id]
        return res

    def _filter_visible_menus(self):
        res = super()._filter_visible_menus()
        if self._is_super_admin():
            menu_my_sub = self.env.ref('havanoposdesk_odoo.menu_my_subscription', raise_if_not_found=False)
            if menu_my_sub and menu_my_sub in res:
                res = res - menu_my_sub
        return res
