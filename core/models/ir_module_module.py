from odoo import models, api

class IrModuleModule(models.Model):
    _inherit = 'ir.module.module'

    @api.model
    def search(self, args, offset=0, limit=None, order=None):
        """
        Hide enterprise modules from the app list to simplify the view
        and maintain a white-labeled experience.
        We filter out any module containing 'enterprise' in the name.
        """
        if self.env.user.havano_role != 'super_admin':
            args = args or []
            args += [('name', 'not ilike', 'enterprise')]
            
        return super(IrModuleModule, self).search(args, offset=offset, limit=limit, order=order)
