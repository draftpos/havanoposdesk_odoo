from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import traceback
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class HavanoposdeskTenant(models.Model):
    _name = 'havanoposdesk.tenant'
    _description = 'Havano POS Desk Tenant'

    def _auto_init(self):
        res = super()._auto_init()
        cr = self.env.cr
        columns = [
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
            ("theme_color", "VARCHAR"),
            ("product_name_format", "VARCHAR"),
            ("restrict_price_modification", "BOOLEAN DEFAULT FALSE"),
            ("payment_status", "VARCHAR"),
            ("enable_fiscalization", "BOOLEAN DEFAULT FALSE"),
            ("is_vat_registered", "BOOLEAN DEFAULT FALSE"),
            ("fiscal_provider", "VARCHAR DEFAULT 'havano_zimra'"),
            ("fiscal_base_url", "VARCHAR"),
            ("fiscal_api_key", "VARCHAR"),
            ("fiscal_api_secret", "VARCHAR"),
            ("fiscal_device_sn", "VARCHAR"),
            ("fiscal_ping_interval", "INTEGER DEFAULT 5"),
        ]
        for col_name, col_type in columns:
            try:
                with cr.savepoint():
                    cr.execute(f"ALTER TABLE havanoposdesk_tenant ADD COLUMN IF NOT EXISTS {col_name} {col_type};")
            except Exception:
                pass

        # Ensure wizard foreign keys have ON DELETE CASCADE so they never block tenant operations
        wizard_tables = [
            'havanoposdesk_tenant_topup_wizard',
            'havanoposdesk_subscription_pay_wizard',
            'havanoposdesk_tenant_upgrade_wizard'
        ]
        for tbl in wizard_tables:
            try:
                with cr.savepoint():
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
        return res

    name = fields.Char(string='Tenant Name', required=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one('res.currency', string='Default Currency', default=lambda self: self.env.ref('base.USD').id)
    allow_multi_currency = fields.Boolean(string='Allow Multi Currency', default=False)
    global_multi_currency_customers = fields.Boolean(string='Global Multi-Currency Customers', default=False)
    global_secondary_currency_id = fields.Many2one('res.currency', string='Default Secondary Currency')
    allow_advanced_pricing = fields.Boolean(string='Allow Advanced Pricing & Multi-UOM', default=True)

    # ZIMRA Fiscalization Settings
    enable_fiscalization = fields.Boolean(string='Enable Fiscalization', default=False)
    is_vat_registered = fields.Boolean(string='VAT Registered Taxpayer', default=True)
    fiscal_provider = fields.Selection([
        ('havano_zimra', 'Havano ZIMRA Cloud'),
        ('axis', 'Axis Virtual API'),
        ('revmax', 'Revmax Hardware')
    ], string='Fiscal Provider', default='havano_zimra')
    fiscal_base_url = fields.Char(string='Base URL', default='https://erpfiscal.havano.online')
    fiscal_api_key = fields.Char(string='API Key')
    fiscal_api_secret = fields.Char(string='API Secret')
    fiscal_device_sn = fields.Char(string='Device Serial No (EFD SN)')
    fiscal_ping_interval = fields.Integer(string='Ping Interval (Minutes)', default=5)

    has_transactions = fields.Boolean(string="Has Transactions", compute="_compute_has_transactions")
    
    def _compute_has_transactions(self):
        for tenant in self:
            Sale = self.env['havanoposdesk.sale'].sudo()
            Purchase = self.env['havanoposdesk.purchase'].sudo()
            Payment = self.env['havanoposdesk.payment'].sudo()
            has_tx = False
            if Sale.search_count([('tenant_id', '=', tenant.id)], limit=1) > 0:
                has_tx = True
            elif Purchase.search_count([('tenant_id', '=', tenant.id)], limit=1) > 0:
                has_tx = True
            elif Payment.search_count([('tenant_id', '=', tenant.id)], limit=1) > 0:
                has_tx = True
            tenant.has_transactions = has_tx
            
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan')
    additional_terminals = fields.Integer(string='Additional Terminals', default=0, help='Extra terminals requested under Custom Plan ($12/terminal)')
    additional_stores = fields.Integer(string='Additional Stores', default=0, help='Auto-calculated store allowance (3 stores per terminal)')
    account_balance = fields.Float(string='Account Balance ($)', default=0.0, help='Prepaid balance/wallet for subscription plans and top-ups.')
    effective_max_stores = fields.Integer(string='Effective Max Stores', compute='_compute_subscription_limits', store=True)
    effective_max_terminals = fields.Integer(string='Effective Max Terminals', compute='_compute_subscription_limits', store=True)
    subscription_total_amount = fields.Float(string='Subscription Total Amount ($)', compute='_compute_subscription_total_amount', store=True)
    subscription_state = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Payment'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Subscription State', default='active')
    subscription_start_date = fields.Date(string='Subscription Start Date')
    subscription_end_date = fields.Date(string='Subscription End Date')

    pending_subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Pending Subscription Plan', help='New plan requested that is pending approval or payment.')
    pending_additional_terminals = fields.Integer(string='Pending Additional Terminals', default=0)
    pending_additional_stores = fields.Integer(string='Pending Additional Stores', default=0)
    pending_subscription_total_amount = fields.Float(string='Pending Total Amount ($)', compute='_compute_pending_subscription_total_amount', store=True)
    has_pending_upgrade = fields.Boolean(string='Has Pending Upgrade', compute='_compute_has_pending_upgrade')
    subscription_payment_ids = fields.One2many('havanoposdesk.subscription.payment', 'tenant_id', string='Transaction History & Top-Ups')
    pending_topup_count = fields.Integer(string='Pending Top-Up Count', compute='_compute_pending_topup_count')

    def _compute_pending_topup_count(self):
        for tenant in self:
            tenant.pending_topup_count = self.env['havanoposdesk.subscription.payment'].search_count([
                ('tenant_id', '=', tenant.id),
                ('payment_type', '=', 'topup'),
                ('state', '=', 'pending')
            ])

    def action_approve_pending_topup(self):
        self.ensure_one()
        is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su
        if not is_super:
            raise ValidationError('Only Super Admins can approve pending top-ups.')
        pending_payments = self.env['havanoposdesk.subscription.payment'].search([
            ('tenant_id', '=', self.id),
            ('payment_type', '=', 'topup'),
            ('state', '=', 'pending')
        ])
        if not pending_payments:
            raise ValidationError('No pending top-up requests found for this tenant.')
        for payment in pending_payments:
            payment.action_approve()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Top-Up Approved',
                'message': 'Approved pending top-up(s) and credited balance.',
                'type': 'success',
                'sticky': False,
            }
        }

    @api.depends('subscription_plan_id', 'subscription_plan_id.max_stores', 'subscription_plan_id.max_terminals', 'subscription_plan_id.is_custom', 'subscription_plan_id.stores_per_terminal', 'additional_stores', 'additional_terminals')
    def _compute_subscription_limits(self):
        for tenant in self:
            plan = tenant.subscription_plan_id
            if not plan:
                tenant.effective_max_stores = 0
                tenant.effective_max_terminals = 0
            elif plan.is_custom:
                stores_per_term = plan.stores_per_terminal or 3
                base_term = plan.max_terminals or 1
                extra_term = max(0, tenant.additional_terminals or 0)
                if extra_term == 0 and tenant.additional_stores > 0:
                    calculated_total_terms = tenant.additional_stores // stores_per_term
                    if calculated_total_terms > base_term:
                        extra_term = calculated_total_terms - base_term
                    elif tenant.additional_stores > (base_term * stores_per_term):
                        extra_term = (tenant.additional_stores - (base_term * stores_per_term)) // stores_per_term
                total_term = base_term + extra_term
                tenant.effective_max_terminals = total_term
                tenant.effective_max_stores = max(total_term * stores_per_term, tenant.additional_stores or 0)
            else:
                tenant.effective_max_terminals = plan.max_terminals or 0
                tenant.effective_max_stores = plan.max_stores or (tenant.effective_max_terminals * 3)

    @api.depends('subscription_plan_id', 'subscription_plan_id.price', 'subscription_plan_id.is_custom', 'subscription_plan_id.extra_terminal_price', 'subscription_plan_id.extra_store_price', 'subscription_plan_id.stores_per_terminal', 'additional_terminals', 'additional_stores')
    def _compute_subscription_total_amount(self):
        for tenant in self:
            plan = tenant.subscription_plan_id
            if not plan:
                tenant.subscription_total_amount = 0.0
            elif plan.is_custom:
                stores_per_term = plan.stores_per_terminal or 3
                base_term = plan.max_terminals or 1
                extra_term = max(0, tenant.additional_terminals or 0)
                if extra_term == 0 and tenant.additional_stores > 0:
                    calculated_total_terms = tenant.additional_stores // stores_per_term
                    if calculated_total_terms > base_term:
                        extra_term = calculated_total_terms - base_term
                extra_price = plan.extra_terminal_price or plan.extra_store_price or 12.0
                tenant.subscription_total_amount = (plan.price or 12.0) + (extra_term * extra_price)
            else:
                tenant.subscription_total_amount = plan.price or 0.0

    @api.depends('pending_subscription_plan_id', 'pending_subscription_plan_id.price', 'pending_subscription_plan_id.is_custom', 'pending_subscription_plan_id.extra_terminal_price', 'pending_subscription_plan_id.extra_store_price', 'pending_subscription_plan_id.stores_per_terminal', 'pending_additional_terminals', 'pending_additional_stores')
    def _compute_pending_subscription_total_amount(self):
        for tenant in self:
            plan = tenant.pending_subscription_plan_id
            if not plan:
                tenant.pending_subscription_total_amount = 0.0
            elif plan.is_custom:
                stores_per_term = plan.stores_per_terminal or 3
                base_term = plan.max_terminals or 1
                extra_term = max(0, tenant.pending_additional_terminals or 0)
                if extra_term == 0 and tenant.pending_additional_stores > 0:
                    calculated_total_terms = tenant.pending_additional_stores // stores_per_term
                    if calculated_total_terms > base_term:
                        extra_term = calculated_total_terms - base_term
                extra_price = plan.extra_terminal_price or plan.extra_store_price or 12.0
                tenant.pending_subscription_total_amount = (plan.price or 12.0) + (extra_term * extra_price)
            else:
                tenant.pending_subscription_total_amount = plan.price or 0.0

    @api.depends('pending_subscription_plan_id')
    def _compute_has_pending_upgrade(self):
        for tenant in self:
            tenant.has_pending_upgrade = bool(tenant.pending_subscription_plan_id)
    theme_color = fields.Selection([
        ('dark', 'Dark'),
        ('light', 'Light')
    ], string="Theme", default='light')
    
    product_name_format = fields.Selection([
        ('uppercase', 'UPPERCASE'),
        ('lowercase', 'lowercase'),
        ('title', 'Title Case'),
        ('asis', 'As-Is')
    ], string='Product Naming Format', default='title')
    
    restrict_price_modification = fields.Boolean(
        string="Restrict Price Modification",
        default=False,
        help="If checked, only Tenant Admins can modify unit prices on sales and purchases."
    )
    
    payment_status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('pending', 'Pending Payment'),
        ('paid', 'Paid')
    ], string='Payment Status', default='unpaid')
    
    user_ids = fields.One2many('res.users', 'tenant_id', string='Users')

    def check_subscription_active(self):
        self.ensure_one()
        if self.subscription_state not in ('expired', 'cancelled', 'pending'):
            return True
            
        if self.subscription_state == 'expired' and self.subscription_end_date:
            grace_days = int(self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.subscription_grace_days', '5'))
            expiry_with_grace = self.subscription_end_date + relativedelta(days=grace_days)
            if fields.Date.context_today(self) <= expiry_with_grace:
                return True
                
        return False

    @api.model
    def get_subscription_info(self):
        """Return subscription status info for the current user's tenant.
        Used by the OWL subscription banner and the mobile API.
        """
        user = self.env.user
        tenant = user.tenant_id
        if not tenant:
            return {'show_banner': False}

        warning_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'havanoposdesk.subscription_expiry_warning_days', '3'))

        days_left = None
        if tenant.subscription_end_date:
            today = fields.Date.context_today(self)
            days_left = (tenant.subscription_end_date - today).days

        is_expiring_soon = days_left is not None and days_left <= warning_days
        is_expired = tenant.subscription_state in ('expired', 'cancelled')

        return {
            'show_banner': is_expiring_soon or is_expired or bool(tenant.pending_subscription_plan_id),
            'state': tenant.subscription_state,
            'days_left': days_left,
            'end_date': str(tenant.subscription_end_date) if tenant.subscription_end_date else None,
            'plan_name': tenant.subscription_plan_id.name if tenant.subscription_plan_id else None,
            'pending_plan_name': tenant.pending_subscription_plan_id.name if tenant.pending_subscription_plan_id else None,
            'has_pending_upgrade': bool(tenant.pending_subscription_plan_id),
            'is_expiring_soon': is_expiring_soon,
            'is_expired': is_expired,
            'warning_days': warning_days,
        }

    api_company_name = fields.Char(string="API Company Name")
    api_currency = fields.Char(string="API Currency", default="USD")
    api_uom = fields.Char(string="API Default UOM", default="Each")
    # Products Sequence Config
    prod_seq_prefix = fields.Char(string='Product Sequence Prefix', default='')
    prod_seq_next = fields.Integer(string='Product Sequence Next Number', default=101)
    prod_seq_padding = fields.Integer(string='Product Sequence Padding', default=0)

    # Stock Adjustments Sequence Config
    stock_adj_seq_prefix = fields.Char(string='Stock Adjustment Sequence Prefix', default='')
    stock_adj_seq_next = fields.Integer(string='Stock Adjustment Sequence Next Number', default=1)
    stock_adj_seq_padding = fields.Integer(string='Stock Adjustment Sequence Padding', default=5)

    # Sales Sequence Config
    allow_credit_sales = fields.Boolean(string='Allow Sales on Credit', default=False)
    sale_seq_prefix = fields.Char(string='Sale Sequence Prefix', default='S')
    sale_seq_next = fields.Integer(string='Sale Sequence Next Number', default=1)
    sale_seq_padding = fields.Integer(string='Sale Sequence Padding', default=4)

    # Quotation Sequence Config
    quotation_seq_prefix = fields.Char(string='Quotation Sequence Prefix', default='Q')
    quotation_seq_next = fields.Integer(string='Quotation Sequence Next Number', default=1)
    quotation_seq_padding = fields.Integer(string='Quotation Sequence Padding', default=4)

    # Sales Return (Credit Note) Sequence Config
    sale_ret_seq_prefix = fields.Char(string='Credit Note Sequence Prefix', default='C')
    sale_ret_seq_next = fields.Integer(string='Credit Note Sequence Next Number', default=1)
    sale_ret_seq_padding = fields.Integer(string='Credit Note Sequence Padding', default=3)

    # Purchases Sequence Config
    purch_seq_prefix = fields.Char(string='Purchase Sequence Prefix', default='PU')
    purch_seq_next = fields.Integer(string='Purchase Sequence Next Number', default=1001)
    purch_seq_padding = fields.Integer(string='Purchase Sequence Padding', default=0)

    # Purchase Return (Debit Note) Sequence Config
    purch_ret_seq_prefix = fields.Char(string='Debit Note Sequence Prefix', default='DEB')
    purch_ret_seq_next = fields.Integer(string='Debit Note Sequence Next Number', default=1001)
    purch_ret_seq_padding = fields.Integer(string='Debit Note Sequence Padding', default=0)

    # Payment In (Receipt) Sequence Config
    pay_in_seq_prefix = fields.Char(string='Payment In Sequence Prefix', default='')
    pay_in_seq_next = fields.Integer(string='Payment In Sequence Next Number', default=1)
    pay_in_seq_padding = fields.Integer(string='Payment In Sequence Padding', default=4)

    # Payment Out Sequence Config
    pay_out_seq_prefix = fields.Char(string='Payment Out Sequence Prefix', default='')
    pay_out_seq_next = fields.Integer(string='Payment Out Sequence Next Number', default=1)
    pay_out_seq_padding = fields.Integer(string='Payment Out Sequence Padding', default=4)

    # Expenses Sequence Config
    exp_seq_prefix = fields.Char(string='Expense Sequence Prefix', default='')
    exp_seq_next = fields.Integer(string='Expense Sequence Next Number', default=1)
    exp_seq_padding = fields.Integer(string='Expense Sequence Padding', default=4)

    # Stock Transfer Sequence Config
    trn_seq_prefix = fields.Char(string='Stock Transfer Sequence Prefix', default='TRN')
    trn_seq_next = fields.Integer(string='Stock Transfer Sequence Next Number', default=1)
    trn_seq_padding = fields.Integer(string='Stock Transfer Sequence Padding', default=4)
    api_cost_center = fields.Char(string="API Cost Center")
    api_warehouse = fields.Char(string="API Warehouse")

    # SaaS backoffice-controlled toggles
    enable_quotations = fields.Boolean(string='Enable Quotations', default=False)
    enable_uom_conversion = fields.Boolean(string='Enable UOM Conversion', default=False)
    enable_payment_entries = fields.Boolean(string='Enable Payment Entries', default=False)
    show_qty_on_hand = fields.Boolean(string='Show Qty on Hand in POS', default=False)
    enable_shift = fields.Boolean(string='Enable Shift Management', default=False)
    enable_tax = fields.Boolean(string='Enable Tax', default=False)
    enable_barcode = fields.Boolean(string='Enable Barcode Scanning', default=False)
    allow_negative_stock = fields.Boolean(string='Allow Negative Stock', default=True)
    allow_edit_item_code = fields.Boolean(string='Allow Editing Item Code', default=False)

    # Global Fiscalization Settings (Defaults for stores)
    enable_fiscalization = fields.Boolean(string='Enable Fiscalization', default=False)
    fiscal_provider = fields.Selection([
        ('havano_zimra', 'Havano ZIMRA Cloud'),
        ('axis', 'Axis Virtual API'),
        ('revmax', 'Revmax Hardware')
    ], string='Fiscal Provider', default='havano_zimra')
    fiscal_base_url = fields.Char(string='Base URL', default='https://erpfiscal.havano.online')
    fiscal_api_key = fields.Char(string='API Key')
    fiscal_api_secret = fields.Char(string='API Secret')
    fiscal_device_sn = fields.Char(string='Default Device Serial No (EFD SN)')
    fiscal_ping_interval = fields.Integer(string='Ping Interval (Minutes)', default=5)
    fiscalized_invoice_heading = fields.Char(string='Fiscalized Invoice Heading', default='Fiscal Tax Invoice')

    powered_by_footer = fields.Char(string='Powered By Footer Text', default='Powered by HavanoERP')



    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('subscription_plan_id'):
                plan = self.env.ref('havanoposdesk_odoo.subscription_plan_1', raise_if_not_found=False)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().search([('name', 'ilike', 'Demo Plan')], limit=1)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().search([], order='id asc', limit=1)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().create({
                        'name': 'Demo Plan (10 Terminals, 10 Stores)',
                        'price': 0.0,
                        'duration_days': 14,
                        'max_stores': 10,
                        'max_terminals': 10,
                        'max_users': 10,
                        'is_custom': False,
                    })
                vals['subscription_plan_id'] = plan.id
                
            if not vals.get('subscription_start_date'):
                vals['subscription_start_date'] = fields.Date.context_today(self)
            if not vals.get('subscription_end_date') and vals.get('subscription_plan_id'):
                plan = self.env['havanoposdesk.subscription.plan'].sudo().browse(vals['subscription_plan_id'])
                duration = getattr(plan, 'duration_days', 30) or 30
                vals['subscription_end_date'] = fields.Date.context_today(self) + relativedelta(days=duration)
            if not vals.get('payment_status'):
                vals['payment_status'] = 'paid'
            if not vals.get('subscription_state'):
                vals['subscription_state'] = 'active'
                
        tenants = super().create(vals_list)
        for tenant in tenants:
            usd_currency = self.env.ref('base.USD', raise_if_not_found=False)
            store_currency_id = tenant.currency_id.id if tenant.currency_id else (usd_currency.id if usd_currency else False)
            
            store = self.env['havanoposdesk.store'].sudo().create({
                'name': tenant.name,
                'tenant_id': tenant.id,
                'is_default': True,
                'currency_id': store_currency_id,
            })
            
            # Auto-create a default terminal
            self.env['havanoposdesk.pos.terminal'].sudo().create({
                'name': 'Pos 1',
                'store_id': store.id,
                'tenant_id': tenant.id,
            })
            
            # Auto-create the 3 default profiles
            self.env['havanoposdesk.user.rights.profile'].sudo().create([
                {
                    'name': 'Super Admin Profile',
                    'tenant_id': tenant.id,
                    'havano_role': 'super_admin'
                },
                {
                    'name': 'Admin Profile',
                    'tenant_id': tenant.id,
                    'havano_role': 'admin'
                },
                {
                    'name': 'Cashier Profile',
                    'tenant_id': tenant.id,
                    'havano_role': 'cashier'
                }
            ])
            
            tenant._seed_default_data()
        return tenants

    def _seed_default_data(self):
        self.ensure_one()
        _logger.info("SEED_DEFAULT_DATA CALLED FOR TENANT: %s (id: %s)", self.name, self.id)
        tenant_id = self.id
        
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        currency_id = self.currency_id.id if self.currency_id else (usd.id if usd else False)
        
        # 1. Default Store
        store = self.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
        if not store:
            store = self.env['havanoposdesk.store'].sudo().create({
                'name': self.name or 'Main Store',
                'tenant_id': tenant_id,
                'is_default': True,
                'currency_id': currency_id,
            })
        store_id = store.id if store else False

        # 2. Default POS Terminal
        terminal = self.env['havanoposdesk.pos.terminal'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
        if not terminal and store:
            self.env['havanoposdesk.pos.terminal'].sudo().create({
                'name': 'Pos 1',
                'store_id': store.id,
                'tenant_id': tenant_id,
            })

        # 3. Default User Rights Profiles
        profiles = [
            ('Super Admin Profile', 'super_admin'),
            ('Admin Profile', 'admin'),
            ('Cashier Profile', 'cashier'),
        ]
        for prof_name, role in profiles:
            existing_prof = self.env['havanoposdesk.user.rights.profile'].sudo().search([
                ('tenant_id', '=', tenant_id),
                '|', ('name', '=ilike', prof_name), ('havano_role', '=', role)
            ], limit=1)
            if not existing_prof:
                self.env['havanoposdesk.user.rights.profile'].sudo().create({
                    'name': prof_name,
                    'tenant_id': tenant_id,
                    'havano_role': role,
                })

        # 4. Customer Group
        cg = self.env['havanoposdesk.customer.group'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
        if not cg:
            cg = self.env['havanoposdesk.customer.group'].sudo().create({
                'name': 'Default Group',
                'tenant_id': tenant_id,
            })

        # 5. Supplier
        supplier = self.env['havanoposdesk.supplier'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
        if not supplier:
            self.env['havanoposdesk.supplier'].sudo().create({
                'name': 'General Supplier',
                'tenant_id': tenant_id,
                'store_id': store_id,
            })

        # 6. Default Deposit Accounts / Payment Methods
        deposit_accounts = [
            ('Cash', 'Cash'),
            ('Bank', 'Bank'),
            ('EcoCash', 'Bank'),
            ('Card / Swipe', 'Bank'),
        ]
        for acc_name, acc_type in deposit_accounts:
            existing_acc = self.env['havanoposdesk.account'].sudo().search([
                ('name', '=ilike', acc_name),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            if not existing_acc:
                self.env['havanoposdesk.account'].sudo().create({
                    'name': acc_name,
                    'type': acc_type,
                    'tenant_id': tenant_id,
                    'currency_id': currency_id,
                    'store_id': store_id,
                    'store_ids': [(6, 0, [store_id])] if store_id else False,
                })

        # 7. Default Expenses Accounts
        expenses = [
            'Electricity',
            'Rent',
            'Utilities',
            'Wages & Salaries',
            'Breakages',
            'Council Licenses',
            'Maintenance',
            'Fuel',
            'Stationery & Office Supplies',
            'Transport & Travel',
            'Advertising & Marketing',
            'Bank Charges',
            'Lunch',
        ]
        for exp in expenses:
            existing_exp = self.env['havanoposdesk.account'].sudo().search([
                ('name', '=ilike', exp),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            if not existing_exp:
                self.env['havanoposdesk.account'].sudo().create({
                    'name': exp,
                    'type': 'Expense',
                    'tenant_id': tenant_id,
                    'currency_id': currency_id,
                    'store_id': store_id,
                    'store_ids': [(6, 0, [store_id])] if store_id else False,
                })

        # 8. Default Customer
        customer = self.env['havanoposdesk.customer'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
        if not customer:
            self.env['havanoposdesk.customer'].sudo().create({
                'name': 'Cash Customer',
                'customer_group_id': cg.id if cg else False,
                'tenant_id': tenant_id,
                'store_ids': [(6, 0, [store_id])] if store_id else False,
            })

        # 9. Default Categories
        categories = ['Basic', 'Beverages']
        for cat_name in categories:
            existing_cat = self.env['havanoposdesk.category'].sudo().search([
                ('name', '=ilike', cat_name),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            if not existing_cat:
                self.env['havanoposdesk.category'].sudo().create({
                    'name': cat_name,
                    'tenant_id': tenant_id,
                    'store_ids': [(6, 0, [store_id])] if store_id else False,
                })

        # 10. Default Pricelist
        retail_pl = self.env['havanoposdesk.pricelist'].sudo().search([
            ('tenant_id', '=', tenant_id),
            ('type', '=', 'selling')
        ], limit=1)
        if not retail_pl:
            retail_pl = self.env['havanoposdesk.pricelist'].sudo().create({
                'name': 'Retail',
                'type': 'selling',
                'tenant_id': tenant_id,
            })

        if store:
            if not store.pricelist_ids:
                store.sudo().write({'pricelist_ids': [(6, 0, [retail_pl.id])]})
            if not store.pricelist_id:
                store.sudo().write({'pricelist_id': retail_pl.id})

        # 11. Default UOMs — 'Each' is first and is the default for products and API
        uoms = ['Each', 'Kg', 'Litre', 'Meter', 'Pieces', 'Box', 'Set']
        for uom in uoms:
            existing_uom = self.env['havanoposdesk.uom'].sudo().search([
                ('name', '=ilike', uom),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            if not existing_uom:
                self.env['havanoposdesk.uom'].sudo().create({
                    'name': uom,
                    'tenant_id': tenant_id,
                })

        # 12. Default Taxes — seeded as INACTIVE so tenant manually activates what they need
        default_taxes = [
            ('VAT', 15.0, 'Sales'),
            ('Exempt', 0.0, 'Sales'),
        ]
        for (tax_name, tax_rate, tax_type) in default_taxes:
            existing_tax = self.env['havanoposdesk.tax'].sudo().search([
                ('name', '=ilike', tax_name),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            if not existing_tax:
                self.env['havanoposdesk.tax'].sudo().create({
                    'name': tax_name,
                    'rate': tax_rate,
                    'tax_type': tax_type,
                    'active': False,
                    'tenant_id': tenant_id,
                })

    def action_approve(self):
        for tenant in self:
            vals = {
                'subscription_state': 'active',
                'payment_status': 'paid',
                'active': True
            }
            target_plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
            if tenant.pending_subscription_plan_id:
                vals['subscription_plan_id'] = tenant.pending_subscription_plan_id.id
                vals['additional_terminals'] = tenant.pending_additional_terminals
                vals['additional_stores'] = tenant.pending_additional_stores
                vals['pending_subscription_plan_id'] = False
                vals['pending_additional_terminals'] = 0
                vals['pending_additional_stores'] = 0

            if target_plan:
                duration = target_plan.duration_days or 30
                start_date = fields.Date.context_today(self)
                vals['subscription_start_date'] = start_date
                vals['subscription_end_date'] = start_date + relativedelta(days=duration)

            tenant.with_context(bypass_subscription_check=True).write(vals)

    def action_expire(self):
        for tenant in self:
            tenant.with_context(bypass_subscription_check=True).write({
                'subscription_state': 'expired'
            })

    def action_cancel(self):
        for tenant in self:
            if tenant.pending_subscription_plan_id:
                vals = {
                    'pending_subscription_plan_id': False,
                    'pending_additional_terminals': 0,
                    'pending_additional_stores': 0,
                }
                if not tenant.subscription_plan_id or tenant.subscription_state != 'active':
                    vals['subscription_state'] = 'cancelled'
                tenant.with_context(bypass_subscription_check=True).write(vals)
            else:
                tenant.with_context(bypass_subscription_check=True).write({
                    'subscription_state': 'cancelled'
                })

    def action_select_plan(self, plan_id, additional_stores=0, additional_terminals=0):
        plan = self.env['havanoposdesk.subscription.plan'].sudo().browse(plan_id)
        if plan.exists() and plan.is_custom:
            stores_per_term = plan.stores_per_terminal or 3
            base_term = plan.max_terminals or 1
            extra_terminals = max(0, int(additional_terminals or 0))
            if extra_terminals == 0 and int(additional_stores or 0) > 0:
                calc_terms = int(additional_stores) // stores_per_term
                if calc_terms > base_term:
                    extra_terminals = calc_terms - base_term
            extra_stores = (base_term + extra_terminals) * stores_per_term
        else:
            extra_terminals = 0
            extra_stores = max(0, int(additional_stores or 0))

        if self.check_subscription_active():
            self.with_context(bypass_subscription_check=True).write({
                'pending_subscription_plan_id': plan_id,
                'pending_additional_terminals': extra_terminals,
                'pending_additional_stores': extra_stores,
            })
        else:
            self.with_context(bypass_subscription_check=True).write({
                'subscription_plan_id': plan_id,
                'additional_terminals': extra_terminals,
                'additional_stores': extra_stores,
                'subscription_state': 'pending',
                'payment_status': 'unpaid'
            })

    def action_pay_and_activate(self):
        for tenant in self:
            plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
            if not plan:
                raise ValidationError('No subscription plan selected.')
            duration = plan.duration_days or 30
            start_date = fields.Date.context_today(self)
            end_date = start_date + relativedelta(days=duration)
            vals = {
                'payment_status': 'paid',
                'subscription_state': 'active',
                'subscription_start_date': start_date,
                'subscription_end_date': end_date,
                'active': True
            }
            if tenant.pending_subscription_plan_id:
                vals['subscription_plan_id'] = tenant.pending_subscription_plan_id.id
                vals['additional_terminals'] = tenant.pending_additional_terminals
                vals['additional_stores'] = tenant.pending_additional_stores
                vals['pending_subscription_plan_id'] = False
                vals['pending_additional_terminals'] = 0
                vals['pending_additional_stores'] = 0
            tenant.with_context(bypass_subscription_check=True).write(vals)

    def action_upgrade_plan(self):
        self.ensure_one()
        return {
            'name': 'Select Subscription Plan',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.tenant.upgrade.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tenant_id': self.id,
            }
        }

    def action_pay_subscription_wizard(self):
        self.ensure_one()
        plan = self.pending_subscription_plan_id or self.subscription_plan_id
        amount = self.pending_subscription_total_amount if self.pending_subscription_plan_id else (self.subscription_total_amount or (plan.price if plan else 0.0))
        return {
            'name': 'Pay & Activate Subscription',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.subscription.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tenant_id': self.id,
                'default_subscription_plan_id': plan.id if plan else False,
                'default_amount': amount,
            }
        }

    def action_topup_wizard(self):
        self.ensure_one()
        return {
            'name': 'Top Up Account Balance',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.tenant.topup.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tenant_id': self.id,
            }
        }

    def action_pay_from_balance(self):
        for tenant in self:
            plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
            if not plan:
                raise ValidationError('No subscription plan selected.')
            amount = tenant.pending_subscription_total_amount if tenant.pending_subscription_plan_id else (tenant.subscription_total_amount or plan.price)
            if tenant.account_balance < amount:
                raise ValidationError(f'Insufficient account balance (${tenant.account_balance:.2f}). Required amount is ${amount:.2f}. Please top up your balance first.')
            
            # Deduct from account_balance
            new_balance = tenant.account_balance - amount
            tenant.with_context(bypass_subscription_check=True).write({'account_balance': new_balance})

            # Create completed payment record
            import time
            ref = f"BAL-{tenant.id}-{plan.id}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
            self.env['havanoposdesk.subscription.payment'].create({
                'tenant_id': tenant.id,
                'subscription_plan_id': plan.id,
                'amount': amount,
                'payment_method': 'account_balance',
                'payment_type': 'subscription',
                'transaction_reference': ref,
                'state': 'done',
            })

            # Activate plan
            tenant.action_pay_and_activate()


    def _get_next_sequence(self, seq_type):
        self.ensure_one()
        # Define field name mapping
        prefix_field = f"{seq_type}_seq_prefix"
        next_field = f"{seq_type}_seq_next"
        padding_field = f"{seq_type}_seq_padding"
        
        # Prevent concurrency issues by selecting this tenant row for update
        self.env.cr.execute("SELECT id FROM havanoposdesk_tenant WHERE id = %s FOR UPDATE", [self.id])
        
        prefix = getattr(self, prefix_field) or ''
        next_val = getattr(self, next_field) or 1
        padding = getattr(self, padding_field) or 0
        
        # Format the sequence number
        seq_str = str(next_val)
        if padding > 0:
            seq_str = seq_str.zfill(padding)
            
        formatted_seq = f"{prefix}{seq_str}"
        
        # Increment and update
        self.write({next_field: next_val + 1})
        
        return formatted_seq

    def write(self, vals):
        restricted_fields = {
            'payment_status', 'subscription_state', 'subscription_start_date',
            'subscription_end_date', 'subscription_plan_id', 'additional_stores',
            'additional_terminals', 'pending_subscription_plan_id',
            'pending_additional_stores', 'pending_additional_terminals',
            'account_balance'
        }
        if self.env.user.havano_role != 'super_admin' and not self.env.su:
            if restricted_fields.intersection(vals.keys()):
                if not self.env.context.get('bypass_subscription_check'):
                    raise ValidationError('You cannot modify subscription details or payment status directly. Please use the "Change/Upgrade Plan" or "Pay & Activate Plan" buttons.')
        return super().write(vals)


class HavanoposdeskTenantUpgradeWizard(models.TransientModel):
    _name = 'havanoposdesk.tenant.upgrade.wizard'
    _description = 'Upgrade Tenant Subscription Plan'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, ondelete='cascade')
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='New Subscription Plan', required=True, ondelete='cascade')
    is_custom = fields.Boolean(string='Is Custom Plan', compute='_compute_plan_details')
    additional_terminals = fields.Integer(string='Additional Terminals Needed', default=0, help='Extra terminals requested ($12 per additional terminal)')
    additional_stores = fields.Integer(string='Included Stores (3 per terminal)', compute='_compute_included_stores')
    extra_terminal_price = fields.Float(string='Extra Price per Terminal ($)', compute='_compute_plan_details')
    computed_total_price = fields.Float(string='Total Monthly Price ($)', compute='_compute_total_price')

    @api.depends('subscription_plan_id', 'additional_terminals')
    def _compute_included_stores(self):
        for wizard in self:
            plan = wizard.subscription_plan_id
            if plan and plan.is_custom:
                base_term = plan.max_terminals or 1
                total_term = base_term + max(0, wizard.additional_terminals or 0)
                wizard.additional_stores = total_term * (plan.stores_per_terminal or 3)
            else:
                wizard.additional_stores = (plan.max_stores if plan else 0) or 3

    @api.depends('subscription_plan_id')
    def _compute_plan_details(self):
        for wizard in self:
            if wizard.subscription_plan_id:
                wizard.is_custom = wizard.subscription_plan_id.is_custom
                wizard.extra_terminal_price = wizard.subscription_plan_id.extra_terminal_price or 12.0
            else:
                wizard.is_custom = False
                wizard.extra_terminal_price = 12.0

    @api.depends('subscription_plan_id', 'subscription_plan_id.price', 'subscription_plan_id.is_custom', 'subscription_plan_id.extra_terminal_price', 'additional_terminals')
    def _compute_total_price(self):
        for wizard in self:
            plan = wizard.subscription_plan_id
            if not plan:
                wizard.computed_total_price = 0.0
            elif plan.is_custom:
                extra = max(0, wizard.additional_terminals or 0)
                extra_price = plan.extra_terminal_price or 12.0
                wizard.computed_total_price = (plan.price or 12.0) + (extra * extra_price)
            else:
                wizard.computed_total_price = plan.price or 0.0

    @api.onchange('tenant_id')
    def _onchange_tenant_id(self):
        if self.tenant_id and self.tenant_id.subscription_plan_id:
            return {'domain': {'subscription_plan_id': [('id', '!=', self.tenant_id.subscription_plan_id.id)]}}
        return {'domain': {'subscription_plan_id': []}}

    def action_confirm(self):
        self.ensure_one()
        if not self.tenant_id:
            raise ValidationError('No tenant associated with the user.')
        target_plan = self.subscription_plan_id
        current_plan = self.tenant_id.pending_subscription_plan_id or self.tenant_id.subscription_plan_id
        if target_plan == current_plan and not target_plan.is_custom:
            raise ValidationError('You cannot select your current subscription plan without changing terminal options.')
        
        extra_terminals = max(0, self.additional_terminals or 0) if self.subscription_plan_id.is_custom else 0
        extra_stores = ((target_plan.max_terminals or 1) + extra_terminals) * (target_plan.stores_per_terminal or 3) if target_plan.is_custom else 0

        if self.tenant_id.check_subscription_active():
            self.tenant_id.with_context(bypass_subscription_check=True).write({
                'pending_subscription_plan_id': self.subscription_plan_id.id,
                'pending_additional_terminals': extra_terminals,
                'pending_additional_stores': extra_stores,
            })
        else:
            self.tenant_id.with_context(bypass_subscription_check=True).write({
                'subscription_plan_id': self.subscription_plan_id.id,
                'additional_terminals': extra_terminals,
                'additional_stores': extra_stores,
                'subscription_state': 'pending',
                'payment_status': 'unpaid'
            })
        return {
            'type': 'ir.actions.act_window_close'
        }



