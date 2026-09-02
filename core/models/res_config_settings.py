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

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        if self.env.user.havano_role in ('admin', 'super_admin') and operation in ('read', 'write', 'create', 'search'):
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    def execute(self):
        if self.env.user.havano_role in ('admin', 'super_admin'):
            return super(ResConfigSettings, self.sudo()).execute()
        return super().execute()

    @api.model
    def default_get(self, fields_list):
        self._ensure_tenant_columns()
        return super().default_get(fields_list)

    @api.model
    def _ensure_tenant_columns(self):
        cr = self.env.cr
        try:
            cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'havanoposdesk_tenant'")
            existing_cols = {row[0] for row in cr.fetchall()}
            cols = [
                ("account_balance", "DOUBLE PRECISION DEFAULT 0.0"),
                ("pending_subscription_plan_id", "INTEGER"),
                ("pending_additional_terminals", "INTEGER DEFAULT 0"),
                ("pending_additional_stores", "INTEGER DEFAULT 0"),
                ("pending_subscription_total_amount", "DOUBLE PRECISION DEFAULT 0.0"),
                ("additional_terminals", "INTEGER DEFAULT 0"),
                ("additional_stores", "INTEGER DEFAULT 0"),
                ("subscription_total_amount", "DOUBLE PRECISION DEFAULT 0.0"),
                ("effective_max_stores", "INTEGER DEFAULT 0"),
                ("effective_max_terminals", "INTEGER DEFAULT 0"),
                ("allow_edit_item_code", "BOOLEAN DEFAULT FALSE"),
                ("allow_negative_stock", "BOOLEAN DEFAULT TRUE"),
                ("enable_tax", "BOOLEAN DEFAULT FALSE"),
                ("enable_barcode", "BOOLEAN DEFAULT FALSE"),
                ("enable_quotations", "BOOLEAN DEFAULT FALSE"),
                ("enable_uom_conversion", "BOOLEAN DEFAULT FALSE"),
                ("enable_payment_entries", "BOOLEAN DEFAULT FALSE"),
                ("show_qty_on_hand", "BOOLEAN DEFAULT FALSE"),
                ("enable_shift", "BOOLEAN DEFAULT FALSE"),
                ("enable_kitchen_settings", "BOOLEAN DEFAULT FALSE"),
                ("theme_color", "VARCHAR"),
                ("product_name_format", "VARCHAR"),
                ("restrict_price_modification", "BOOLEAN DEFAULT FALSE"),
                ("payment_status", "VARCHAR"),
                ("enable_manufacturing", "BOOLEAN DEFAULT FALSE"),
                ("enable_payroll", "BOOLEAN DEFAULT FALSE"),
                ("payroll_url", "VARCHAR"),
                ("stock_decimal_places", "INTEGER DEFAULT 3"),
                ("do_not_round_stock", "BOOLEAN DEFAULT FALSE"),
                ("expenses_require_approval", "BOOLEAN DEFAULT FALSE"),
            ]
            for col_name, col_type in cols:
                if col_name not in existing_cols:
                    cr.execute(f"ALTER TABLE havanoposdesk_tenant ADD COLUMN {col_name} {col_type};")

            # Ensure wizard foreign keys have ON DELETE CASCADE so they never block tenant operations
            wizard_tables = [
                'havanoposdesk_tenant_topup_wizard',
                'havanoposdesk_subscription_pay_wizard',
                'havanoposdesk_tenant_upgrade_wizard'
            ]
            for tbl in wizard_tables:
                try:
                    cr.execute(f"SELECT to_regclass('{tbl}');")
                    if cr.fetchone()[0]:
                        cr.execute(f"""
                            SELECT conname 
                            FROM pg_constraint 
                            WHERE conrelid = '{tbl}'::regclass 
                              AND confrelid = 'havanoposdesk_tenant'::regclass;
                        """)
                        for row in cr.fetchall():
                            con_name = row[0]
                            cr.execute(f"ALTER TABLE {tbl} DROP CONSTRAINT IF EXISTS \"{con_name}\";")
                            cr.execute(f"ALTER TABLE {tbl} ADD CONSTRAINT \"{con_name}\" FOREIGN KEY (tenant_id) REFERENCES havanoposdesk_tenant(id) ON DELETE CASCADE;")
                except Exception:
                    pass
        except Exception:
            pass

    biz_product_name_format = fields.Selection(
        related='tenant_id.product_name_format',
        readonly=False,
        string="Product Name Formatting"
    )

    biz_restrict_price_modification = fields.Boolean(
        related='tenant_id.restrict_price_modification',
        readonly=False,
        string="Restrict Price Modification"
    )

    biz_restaurant_mode_enabled = fields.Boolean(
        related='tenant_id.restaurant_mode_enabled',
        readonly=False,
        string="Enable Restaurant Mode"
    )

    biz_allow_negative_stock = fields.Boolean(
        string="Allow Negative Stock",
        related='tenant_id.allow_negative_stock',
        readonly=False,
        help="If enabled, you can sell items even if their stock quantity goes below zero. Purchasing items will compensate for the negative balance."
    )

    biz_allow_edit_item_code = fields.Boolean(
        string="Allow Editing Product Code",
        related='tenant_id.allow_edit_item_code',
        readonly=False,
        help="If enabled, users will be allowed to edit the product codes (item codes) on products."
    )

    biz_stock_decimal_places = fields.Integer(
        string="Stock / Quantity Decimal Places",
        related='tenant_id.stock_decimal_places',
        readonly=False,
        help="Number of decimal places used for quantities and stock (minimum 1)."
    )

    biz_do_not_round_stock = fields.Boolean(
        string="Do Not Round Quantities (Truncate)",
        related='tenant_id.do_not_round_stock',
        readonly=False,
        help="If enabled, decimal values will be truncated instead of rounded (e.g. 1.67 with 1 decimal place becomes 1.6)."
    )

    biz_expenses_require_approval = fields.Boolean(
        string="Expenses Require Approval",
        related='tenant_id.expenses_require_approval',
        readonly=False,
        help="If enabled, expenses submitted by cashiers from the POS will require manager approval before cash is deducted."
    )

    def _default_tenant_id(self):
        tenant = self.env.user.tenant_id
        if not tenant:
            tenant = self.env['havanoposdesk.tenant'].sudo().search([], limit=1)
        return tenant.id if tenant else False

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string="Tenant",
        ondelete='cascade',
        default=_default_tenant_id
    )

    biz_currency_id = fields.Many2one(
        'res.currency', 
        string="Business Currency",
        related='tenant_id.currency_id',
        readonly=False
    )
    biz_logo = fields.Image(
        string="Business Logo",
        related='tenant_id.logo',
        readonly=False
    )
    has_transactions = fields.Boolean(
        string="Has Transactions",
        related='tenant_id.has_transactions'
    )
    biz_allow_multi_currency = fields.Boolean(
        string="Allow Multi Currency",
        related='tenant_id.allow_multi_currency',
        readonly=False
    )
    biz_global_multi_currency_customers = fields.Boolean(
        string="Global Multi-Currency Customers",
        related='tenant_id.global_multi_currency_customers',
        readonly=False
    )
    biz_global_secondary_currency_id = fields.Many2one(
        'res.currency',
        string="Global Secondary Currency",
        related='tenant_id.global_secondary_currency_id',
        readonly=False
    )
    biz_account_balance = fields.Float(
        string="Account Balance ($)",
        related='tenant_id.account_balance',
        readonly=True
    )

    def action_open_topup_wizard(self):
        self.ensure_one()
        tenant = self.tenant_id or self.env.user.tenant_id
        if not tenant:
            tenant = self.env['havanoposdesk.tenant'].sudo().search([], limit=1)
        if tenant:
            return tenant.action_topup_wizard()

    biz_allow_advanced_pricing = fields.Boolean(
        string="Allow Advanced Pricing",
        related='tenant_id.allow_advanced_pricing',
        readonly=False
    )

    # SaaS backoffice-controlled  related settings
    biz_enable_tax = fields.Boolean(
        string="Enable Tax",
        related='tenant_id.enable_tax',
        readonly=False
    )
    biz_enable_barcode = fields.Boolean(
        string="Enable Barcode Scanning",
        related='tenant_id.enable_barcode',
        readonly=False
    )
    biz_enable_quotations = fields.Boolean(
        string="Enable Quotations",
        related='tenant_id.enable_quotations',
        readonly=False
    )
    biz_enable_uom_conversion = fields.Boolean(
        string="Enable UOM Conversion",
        related='tenant_id.enable_uom_conversion',
        readonly=False
    )
    biz_enable_payment_entries = fields.Boolean(
        string="Enable Payment Entries",
        related='tenant_id.enable_payment_entries',
        readonly=False
    )
    biz_show_qty_on_hand = fields.Boolean(
        string="Show Qty on Hand in POS",
        related='tenant_id.show_qty_on_hand',
        readonly=False
    )
    biz_enable_shift = fields.Boolean(
        string="Enable Shift Management",
        related='tenant_id.enable_shift',
        readonly=False
    )
    biz_enable_kitchen_settings = fields.Boolean(
        string="Enable Kitchen Settings",
        related='tenant_id.enable_kitchen_settings',
        readonly=False
    )
    biz_enable_manufacturing = fields.Boolean(
        string="Enable Manufacturing",
        related='tenant_id.enable_manufacturing',
        readonly=False
    )

    biz_enable_payroll = fields.Boolean(
        related='tenant_id.enable_payroll',
        readonly=False,
        string="Enable Payroll"
    )

    biz_payroll_url = fields.Char(
        related='tenant_id.payroll_url',
        readonly=False,
        string="Payroll URL"
    )

    # ZIMRA Fiscalization Settings
    biz_enable_fiscalization = fields.Boolean(
        string="Enable Fiscalization",
        related='tenant_id.enable_fiscalization',
        readonly=False
    )
    biz_fiscal_provider = fields.Selection(
        string="Fiscal Provider",
        related='tenant_id.fiscal_provider',
        readonly=False
    )
    biz_fiscal_base_url = fields.Char(
        string="Base URL",
        related='tenant_id.fiscal_base_url',
        readonly=False
    )
    biz_fiscal_api_key = fields.Char(
        string="API Key",
        related='tenant_id.fiscal_api_key',
        readonly=False
    )
    biz_fiscal_api_secret = fields.Char(
        string="API Secret",
        related='tenant_id.fiscal_api_secret',
        readonly=False
    )
    biz_fiscal_device_sn = fields.Char(
        string="Default Device Serial No (EFD SN)",
        related='tenant_id.fiscal_device_sn',
        readonly=False
    )
    biz_fiscal_ping_interval = fields.Integer(
        string="Ping Interval (Minutes)",
        related='tenant_id.fiscal_ping_interval',
        readonly=False
    )
    biz_fiscalized_invoice_heading = fields.Char(
        string="Fiscalized Invoice Heading",
        related='tenant_id.fiscalized_invoice_heading',
        readonly=False
    )
    biz_powered_by_footer = fields.Char(
        string="Powered By Footer Text",
        related='tenant_id.powered_by_footer',
        readonly=False
    )



    def action_ping_zimra_device(self):
        self.ensure_one()
        class ConfigWrapper:
            def __init__(self, base_url, api_key, api_secret, device_sn):
                self.fiscal_base_url = base_url
                self.fiscal_api_key = api_key
                self.fiscal_api_secret = api_secret
                self.fiscal_device_sn = device_sn

        base_url = self.biz_fiscal_base_url or (self.tenant_id and self.tenant_id.fiscal_base_url)
        api_key = self.biz_fiscal_api_key or (self.tenant_id and self.tenant_id.fiscal_api_key)
        api_secret = self.biz_fiscal_api_secret or (self.tenant_id and self.tenant_id.fiscal_api_secret)
        device_sn = self.biz_fiscal_device_sn or (self.tenant_id and self.tenant_id.fiscal_device_sn)

        if not base_url:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ping Failed',
                    'message': 'Base URL is required to ping ZIMRA device.',
                    'type': 'danger',
                    'sticky': True,
                }
            }

        cfg = ConfigWrapper(base_url, api_key, api_secret, device_sn)
        from .fiscal_service import get_zimra_service
        service = get_zimra_service(self.env)
        res = service.ping_device(cfg)
        if res.get('success'):
            data = res.get('data', {})
            msg = f"Connected! Device SN: {data.get('device_sn', 'OK')} | Status: Online"
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ping Successful',
                    'message': msg,
                    'type': 'success',
                    'sticky': False,
                }
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Ping Failed',
                    'message': res.get('error', 'Connection failed'),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    # Product Sequence
    biz_prod_seq_prefix = fields.Char(string="Product Sequence Prefix", related='tenant_id.prod_seq_prefix', readonly=False)
    biz_prod_seq_next = fields.Integer(string="Product Sequence Next Number", related='tenant_id.prod_seq_next', readonly=False)
    biz_prod_seq_padding = fields.Integer(string="Product Sequence Padding", related='tenant_id.prod_seq_padding', readonly=False)

    # Stock Adjustments Sequence
    biz_stock_adj_seq_prefix = fields.Char(string="Stock Adjustment Sequence Prefix", related='tenant_id.stock_adj_seq_prefix', readonly=False)
    biz_stock_adj_seq_next = fields.Integer(string="Stock Adjustment Sequence Next Number", related='tenant_id.stock_adj_seq_next', readonly=False)
    biz_stock_adj_seq_padding = fields.Integer(string="Stock Adjustment Sequence Padding", related='tenant_id.stock_adj_seq_padding', readonly=False)

    # Sales Sequence
    biz_allow_credit_sales = fields.Boolean(string="Allow Sales on Credit", related='tenant_id.allow_credit_sales', readonly=False)
    biz_default_payment_status = fields.Selection(
        related='tenant_id.default_payment_status',
        readonly=False,
        string="Default Payment Mode"
    )
    biz_sale_seq_prefix = fields.Char(string="Sale Sequence Prefix", related='tenant_id.sale_seq_prefix', readonly=False)
    biz_sale_seq_next = fields.Integer(string="Sale Sequence Next Number", related='tenant_id.sale_seq_next', readonly=False)
    biz_sale_seq_padding = fields.Integer(string="Sale Sequence Padding", related='tenant_id.sale_seq_padding', readonly=False)

    # Sales Return (Credit Note) Sequence
    biz_sale_ret_seq_prefix = fields.Char(string="Credit Note Sequence Prefix", related='tenant_id.sale_ret_seq_prefix', readonly=False)
    biz_sale_ret_seq_next = fields.Integer(string="Credit Note Sequence Next Number", related='tenant_id.sale_ret_seq_next', readonly=False)
    biz_sale_ret_seq_padding = fields.Integer(string="Credit Note Sequence Padding", related='tenant_id.sale_ret_seq_padding', readonly=False)

    # Purchases Sequence
    biz_purch_seq_prefix = fields.Char(string="Purchase Sequence Prefix", related='tenant_id.purch_seq_prefix', readonly=False)
    biz_purch_seq_next = fields.Integer(string="Purchase Sequence Next Number", related='tenant_id.purch_seq_next', readonly=False)
    biz_purch_seq_padding = fields.Integer(string="Purchase Sequence Padding", related='tenant_id.purch_seq_padding', readonly=False)

    # Purchase Return (Debit Note) Sequence
    biz_purch_ret_seq_prefix = fields.Char(string="Debit Note Sequence Prefix", related='tenant_id.purch_ret_seq_prefix', readonly=False)
    biz_purch_ret_seq_next = fields.Integer(string="Debit Note Sequence Next Number", related='tenant_id.purch_ret_seq_next', readonly=False)
    biz_purch_ret_seq_padding = fields.Integer(string="Debit Note Sequence Padding", related='tenant_id.purch_ret_seq_padding', readonly=False)

    # Payment In Sequence
    biz_pay_in_seq_prefix = fields.Char(string="Payment In Sequence Prefix", related='tenant_id.pay_in_seq_prefix', readonly=False)
    biz_pay_in_seq_next = fields.Integer(string="Payment In Sequence Next Number", related='tenant_id.pay_in_seq_next', readonly=False)
    biz_pay_in_seq_padding = fields.Integer(string="Payment In Sequence Padding", related='tenant_id.pay_in_seq_padding', readonly=False)

    # Payment Out Sequence
    biz_pay_out_seq_prefix = fields.Char(string="Payment Out Sequence Prefix", related='tenant_id.pay_out_seq_prefix', readonly=False)
    biz_pay_out_seq_next = fields.Integer(string="Payment Out Sequence Next Number", related='tenant_id.pay_out_seq_next', readonly=False)
    biz_pay_out_seq_padding = fields.Integer(string="Payment Out Sequence Padding", related='tenant_id.pay_out_seq_padding', readonly=False)

    # Expenses Sequence
    biz_exp_seq_prefix = fields.Char(string="Expense Sequence Prefix", related='tenant_id.exp_seq_prefix', readonly=False)
    biz_exp_seq_next = fields.Integer(string="Expense Sequence Next Number", related='tenant_id.exp_seq_next', readonly=False)
    biz_exp_seq_padding = fields.Integer(string="Expense Sequence Padding", related='tenant_id.exp_seq_padding', readonly=False)

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
    havano_pwa_small_icon = fields.Char(
        string="PWA Small Icon",
        config_parameter="havanoposdesk.pwa_small_icon",
        default="/havanoposdesk_odoo/static/src/img/havano-icon-192x192.png",
    )
    havano_pwa_large_icon = fields.Char(
        string="PWA Large Icon",
        config_parameter="havanoposdesk.pwa_large_icon",
        default="/havanoposdesk_odoo/static/src/img/havano-icon-512x512.png",
    )
    havano_pwa_app_icon = fields.Char(
        string="PWA App Icon",
        config_parameter="havanoposdesk.pwa_app_icon",
        default="/havanoposdesk_odoo/static/src/img/havano-icon-512x512.png",
    )
    havano_pwa_background_color = fields.Char(
        string="PWA Background Color",
        config_parameter="havanoposdesk.pwa_background_color",
        default="#714B67",
    )
    havano_bot_email = fields.Char(
        string="Bot Email",
        config_parameter="havanoposdesk.bot_email",
        default="bot@havano.cloud",
    )
    havano_favicon = fields.Char(
        string="X Icon",
        config_parameter="havanoposdesk.favicon",
        default="/havanoposdesk_odoo/static/src/img/favicon.png",
    )
    havano_support_phone = fields.Char(
        string="Support Phone",
        config_parameter="havanoposdesk.support_phone",
        default="+263 779 9734 028",
        help="Support phone number displayed on the login page."
    )
    havano_sales_phone = fields.Char(
        string="Sales Phone",
        config_parameter="havanoposdesk.sales_phone",
        default="+263 778 078 440",
        help="Sales phone number displayed on the login page."
    )
    havano_whatsapp_phone = fields.Char(
        string="WhatsApp Phone",
        config_parameter="havanoposdesk.whatsapp_phone",
        default="+263 779 9734 028",
        help="WhatsApp contact number displayed on the login page."
    )

    def set_values(self):
        icp = self.env['ir.config_parameter'].sudo()
        old_base = icp.get_param('havanoposdesk.web_base_url', 'havano')
        super().set_values()
        
        # Explicitly save tenant related fields to ensure they persist
        if self.tenant_id:
            self.tenant_id.sudo().write({
                'enable_payroll': self.biz_enable_payroll,
                'payroll_url': self.biz_payroll_url,
            })
            
        bot_name = icp.get_param('havanoposdesk.bot_name', 'HavanoBot')
        bot_email = icp.get_param('havanoposdesk.bot_email', 'bot@havano.cloud')
        # Rename OdooBot in the database
        bot_partner = self.env.ref('base.partner_root', raise_if_not_found=False)
        if bot_partner:
            bot_partner.sudo().write({
                'name': bot_name,
                'email': bot_email,
            })
            
        # Clear the registry cache so that `has_group` overrides take effect instantly for menu visibility
        self.env.registry.clear_cache()

        new_base = icp.get_param('havanoposdesk.web_base_url', 'havano')
        if old_base != new_base:
            return {
                'type': 'ir.actions.act_url',
                'url': f'/{new_base}',
                'target': 'self',
            }

    # ── Bugsink Error Logging Settings ────────────────────────────────
    havano_bugsink_base_url = fields.Char(
        string="Bugsink Base URL",
        config_parameter="havanoposdesk.bugsink_base_url",
        help="Base URL for your Bugsink instance (e.g. https://bugsink.example.com)"
    )
    havano_bugsink_project_id = fields.Integer(
        string="Bugsink Project ID",
        config_parameter="havanoposdesk.bugsink_project_id",
        help="The numeric Project ID from Bugsink."
    )
    havano_bugsink_api_token = fields.Char(
        string="Bugsink API Token",
        config_parameter="havanoposdesk.bugsink_api_token",
        help="The Bearer API token used for authenticating with Bugsink."
    )

    havano_subscription_grace_days = fields.Integer(
        string="Subscription Grace Days",
        config_parameter="havanoposdesk.subscription_grace_days",
        default=5,
        help="The amount of time (in days) a user's subscription can be expired before access is blocked."
    )

    def action_apply_global_multi_currency(self):
        self.ensure_one()
        if not self.biz_global_multi_currency_customers:
            return
        customers = self.env['havanoposdesk.customer'].sudo().search([('tenant_id', '=', self.tenant_id.id)])
        customers.write({
            'allow_multi_currency': True,
            'secondary_currency_id': self.biz_global_secondary_currency_id.id if self.biz_global_secondary_currency_id else False
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'All existing customers have been updated to use the global multi-currency setting.',
                'type': 'success',
                'sticky': False,
            }
        }
    havano_subscription_expiry_warning_days = fields.Integer(
        string="Subscription Expiry Warning Days",
        config_parameter="havanoposdesk.subscription_expiry_warning_days",
        default=3,
        help="Number of days before subscription expiry to start showing warning banners to users."
    )

