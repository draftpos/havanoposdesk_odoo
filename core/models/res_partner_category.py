from odoo import models, fields, api

class ResPartnerCategory(models.Model):
    _inherit = 'res.partner.category'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        index=True,
        default=lambda self: self.env.user.tenant_id.id if getattr(self.env.user, 'tenant_id', None) else False
    )

    @api.model
    def _register_hook(self):
        super()._register_hook()
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("ALTER TABLE res_partner_category ADD COLUMN IF NOT EXISTS tenant_id INTEGER;")
        except Exception:
            pass
