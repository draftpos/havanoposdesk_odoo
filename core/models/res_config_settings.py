from odoo import api, models, fields

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    is_super_user = fields.Boolean(
        string="Is Super User",
        compute="_compute_is_super_user"
    )

    is_custom_configs = fields.Boolean(
        string="Is Custom Configs",
        compute="_compute_is_custom_configs"
    )

    @api.depends_context('uid')
    def _compute_is_super_user(self):
        is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su
        for record in self:
            record.is_super_user = is_super

    @api.depends_context('is_custom_configs', 'uid')
    def _compute_is_custom_configs(self):
        is_custom = self.env.context.get('is_custom_configs', False)
        if not is_custom:
            params = self.env.context.get('params', {})
            menu_id = params.get('menu_id')
            if menu_id:
                menu = self.env['ir.ui.menu'].sudo().browse(menu_id)
                if menu.exists():
                    native_menu_ids = []
                    admin_menu = self.env.ref('base.menu_administration', raise_if_not_found=False)
                    if admin_menu:
                        native_menu_ids.append(admin_menu.id)
                    config_menu = self.env.ref('base.menu_config', raise_if_not_found=False)
                    if config_menu:
                        native_menu_ids.append(config_menu.id)
                    
                    if menu.id in native_menu_ids or (menu.parent_id and menu.parent_id.id in native_menu_ids):
                        is_custom = False
                    else:
                        is_custom = True
        for record in self:
            record.is_custom_configs = is_custom

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        if self.env.user.havano_role in ('admin', 'super_admin') and operation in ('read', 'write', 'create', 'search'):
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    def execute(self):
        if self.env.user.havano_role in ('admin', 'super_admin'):
            return super(ResConfigSettings, self.sudo()).execute()
        return super().execute()


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
    biz_allow_advanced_pricing = fields.Boolean(
        string="Allow Advanced Pricing",
        related='tenant_id.allow_advanced_pricing',
        readonly=False
    )

    havano_verification_grace_number = fields.Integer(
        string="Verification Grace Number",
        config_parameter="havanoposdesk.verification_grace_number",
        default=24,
        help="The amount of time a user has to verify their email before their account is suspended."
    )
    havano_verification_grace_unit = fields.Selection([
        ('hours', 'Hours'),
        ('days', 'Days')
    ], string="Verification Grace Unit",
        config_parameter="havanoposdesk.verification_grace_unit",
        default='hours',
        help="Unit of time for the grace period (Hours or Days)."
    )

    # ── White-label settings ──────────────────────────────────────────
    havano_app_name = fields.Char(
        string="App Name",
        config_parameter="web.web_app_name",
        default="Havano",
        help="The name shown as the PWA app name and browser title."
    )
    havano_web_base_url = fields.Char(
        string="Web Base URL Path",
        config_parameter="havanoposdesk.web_base_url",
        default="havano",
        help="Custom URL path prefix (e.g. 'havano' makes the app accessible at /havano)."
    )
    havano_theme_color = fields.Char(
        string="Theme Color",
        config_parameter="havanoposdesk.theme_color",
        default="#714B67",
        help="PWA theme color (hex)."
    )
    havano_bot_name = fields.Char(
        string="Bot Name",
        config_parameter="havanoposdesk.bot_name",
        default="HavanoBot",
        help="The name of the chatbot visible in the Discuss sidebar."
    )
    havano_vendor_url = fields.Char(
        string="Vendor URL",
        config_parameter="havanoposdesk.vendor_url",
        default="https://havano.cloud",
        help="Vendor website URL shown in the login page footer."
    )
    havano_vendor_domain = fields.Char(
        string="Vendor Domain",
        config_parameter="havanoposdesk.vendor_domain",
        default="havano.cloud",
        help="Vendor domain shown in the login page footer."
    )
