from odoo import api, models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_super_user = fields.Boolean(
        string="Is Super User",
        compute="_compute_is_super_user"
    )

    @api.depends_context('uid')
    def _compute_is_super_user(self):
        is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su
        for record in self:
            record.is_super_user = is_super


    havano_allow_negative_stock = fields.Boolean(
        string="Allow Negative Stock",
        config_parameter="havanoposdesk.allow_negative_stock",
        default=True,
        help="If enabled, you can sell items even if their stock quantity goes below zero. Purchasing items will compensate for the negative balance."
    )

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string="Tenant",
        default=lambda self: self.env.user.tenant_id.id
    )

    biz_currency_id = fields.Many2one(
        'res.currency', 
        string="Business Currency",
        related='tenant_id.currency_id',
        readonly=False
    )
    biz_allow_multi_currency = fields.Boolean(
        string="Allow Multi Currency",
        related='tenant_id.allow_multi_currency',
        readonly=False
    )
