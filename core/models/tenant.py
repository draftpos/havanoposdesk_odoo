from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging
import traceback
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

class HavanoposdeskTenant(models.Model):
    _name = 'havanoposdesk.tenant'
    _description = 'Havano POS Desk Tenant'

    name = fields.Char(string='Tenant Name', required=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one('res.currency', string='Default Currency', default=lambda self: self.env.ref('base.USD').id)
    allow_multi_currency = fields.Boolean(string='Allow Multi Currency', default=False)
    global_multi_currency_customers = fields.Boolean(string='Global Multi-Currency Customers', default=False)
    global_secondary_currency_id = fields.Many2one('res.currency', string='Default Secondary Currency')
    allow_advanced_pricing = fields.Boolean(string='Allow Advanced Pricing & Multi-UOM', default=True)
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
    additional_stores = fields.Integer(string='Additional Stores', default=0, help='Extra stores requested under Custom Plan ($12/store)')
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
    pending_additional_stores = fields.Integer(string='Pending Additional Stores', default=0)
    pending_subscription_total_amount = fields.Float(string='Pending Total Amount ($)', compute='_compute_pending_subscription_total_amount', store=True)
    has_pending_upgrade = fields.Boolean(string='Has Pending Upgrade', compute='_compute_has_pending_upgrade')

    @api.depends('subscription_plan_id', 'subscription_plan_id.max_stores', 'subscription_plan_id.max_terminals', 'subscription_plan_id.is_custom', 'additional_stores')
    def _compute_subscription_limits(self):
        for tenant in self:
            plan = tenant.subscription_plan_id
            if not plan:
                tenant.effective_max_stores = 0
                tenant.effective_max_terminals = 0
            elif plan.is_custom:
                extra = max(0, tenant.additional_stores or 0)
                tenant.effective_max_stores = (plan.max_stores or 0) + extra
                tenant.effective_max_terminals = (plan.max_terminals or 0) + extra
            else:
                tenant.effective_max_stores = plan.max_stores or 0
                tenant.effective_max_terminals = plan.max_terminals or 0

    @api.depends('subscription_plan_id', 'subscription_plan_id.price', 'subscription_plan_id.is_custom', 'subscription_plan_id.extra_store_price', 'additional_stores')
    def _compute_subscription_total_amount(self):
        for tenant in self:
            plan = tenant.subscription_plan_id
            if not plan:
                tenant.subscription_total_amount = 0.0
            elif plan.is_custom:
                extra = max(0, tenant.additional_stores or 0)
                extra_price = plan.extra_store_price or 12.0
                tenant.subscription_total_amount = (plan.price or 0.0) + (extra * extra_price)
            else:
                tenant.subscription_total_amount = plan.price or 0.0

    @api.depends('pending_subscription_plan_id', 'pending_subscription_plan_id.price', 'pending_subscription_plan_id.is_custom', 'pending_subscription_plan_id.extra_store_price', 'pending_additional_stores')
    def _compute_pending_subscription_total_amount(self):
        for tenant in self:
            plan = tenant.pending_subscription_plan_id
            if not plan:
                tenant.pending_subscription_total_amount = 0.0
            elif plan.is_custom:
                extra = max(0, tenant.pending_additional_stores or 0)
                extra_price = plan.extra_store_price or 12.0
                tenant.pending_subscription_total_amount = (plan.price or 0.0) + (extra * extra_price)
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
    sale_seq_padding = fields.Integer(string='Sale Sequence Padding', default=3)

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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('subscription_plan_id'):
                plan = self.env.ref('havanoposdesk_odoo.subscription_plan_1', raise_if_not_found=False)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().search([('name', 'ilike', 'Plan 1')], limit=1)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().search([], order='id asc', limit=1)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().create({
                        'name': 'Plan 1 (1 Store, 1 Terminal)',
                        'price': 15.0,
                        'duration_days': 30,
                        'max_stores': 1,
                        'max_terminals': 1,
                        'max_users': 2,
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
        _logger.info("SEED_DEFAULT_DATA CALLED VIA ORM")
        store = self.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', self.id)], limit=1)
        store_id = store.id if store else False
        tenant_id = self.id
        
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        currency_id = self.currency_id.id if self.currency_id else (usd.id if usd else False)
        
        # 1. Customer Group
        cg = self.env['havanoposdesk.customer.group'].sudo().create({
            'name': 'Default Group',
            'tenant_id': tenant_id,
        })
        
        # 2. Supplier
        self.env['havanoposdesk.supplier'].sudo().create({
            'name': 'General Supplier',
            'tenant_id': tenant_id,
            'store_id': store_id,
        })
        
        # 3. Default Deposit Account
        self.env['havanoposdesk.account'].sudo().create({
            'name': 'Cash',
            'type': 'Cash',
            'tenant_id': tenant_id,
            'currency_id': currency_id,
        })
        
        # 4. Default Expenses Account
        expenses = ['Electricity', 'Rent', 'Utilities', 'Wages & Salaries', 'Breakages', 'Council Licenses', 'Maintanences', 'Fuel']
        for exp in expenses:
            self.env['havanoposdesk.account'].sudo().create({
                'name': exp,
                'type': 'Expense',
                'tenant_id': tenant_id,
                'currency_id': currency_id,
            })
            
        # 5. Default Customer
        self.env['havanoposdesk.customer'].sudo().create({
            'name': 'Cash Customer',
            'customer_group_id': cg.id,
            'tenant_id': tenant_id,
            'store_ids': [(6, 0, [store_id])] if store_id else False,
        })
        
        # 6. Default Categories
        self.env['havanoposdesk.category'].sudo().create([
            {
                'name': 'Basic',
                'tenant_id': tenant_id,
                'store_ids': [(6, 0, [store_id])] if store_id else False,
            },
            {
                'name': 'Beverages',
                'tenant_id': tenant_id,
                'store_ids': [(6, 0, [store_id])] if store_id else False,
            }
        ])
        
        # 7. Default Pricelist
        retail_pl = self.env['havanoposdesk.pricelist'].sudo().search([
            ('tenant_id', '=', tenant_id),
            ('name', '=ilike', 'Retail')
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
        
        # 8. Default UOMs — 'Each' is first and is the default for products and API
        uoms = ['Each', 'Kg', 'Litre', 'Meter', 'Pieces', 'Box', 'Set']
        for uom in uoms:
            self.env['havanoposdesk.uom'].sudo().create({
                'name': uom,
                'tenant_id': tenant_id,
            })
        
        # 9. Default Taxes — seeded as INACTIVE so tenant manually activates what they need
        default_taxes = [
            ('VAT', 15.0, 'Sales'),
            ('Exempt', 0.0, 'Sales'),
        ]
        for (tax_name, tax_rate, tax_type) in default_taxes:
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
                vals['additional_stores'] = tenant.pending_additional_stores
                vals['pending_subscription_plan_id'] = False
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
                    'pending_additional_stores': 0
                }
                if not tenant.subscription_plan_id or tenant.subscription_state != 'active':
                    vals['subscription_state'] = 'cancelled'
                tenant.with_context(bypass_subscription_check=True).write(vals)
            else:
                tenant.with_context(bypass_subscription_check=True).write({
                    'subscription_state': 'cancelled'
                })

    def action_select_plan(self, plan_id, additional_stores=0):
        plan = self.env['havanoposdesk.subscription.plan'].sudo().browse(plan_id)
        extra_stores = max(0, int(additional_stores or 0)) if (plan.exists() and plan.is_custom) else 0
        if self.check_subscription_active():
            self.with_context(bypass_subscription_check=True).write({
                'pending_subscription_plan_id': plan_id,
                'pending_additional_stores': extra_stores,
            })
        else:
            self.with_context(bypass_subscription_check=True).write({
                'subscription_plan_id': plan_id,
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
                vals['additional_stores'] = tenant.pending_additional_stores
                vals['pending_subscription_plan_id'] = False
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
            'pending_subscription_plan_id', 'pending_additional_stores'
        }
        if self.env.user.havano_role != 'super_admin' and not self.env.su:
            if restricted_fields.intersection(vals.keys()):
                if not self.env.context.get('bypass_subscription_check'):
                    raise ValidationError('You cannot modify subscription details or payment status directly. Please use the "Change/Upgrade Plan" or "Pay & Activate Plan" buttons.')
        return super().write(vals)


class HavanoposdeskTenantUpgradeWizard(models.TransientModel):
    _name = 'havanoposdesk.tenant.upgrade.wizard'
    _description = 'Upgrade Tenant Subscription Plan'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='New Subscription Plan', required=True)
    is_custom = fields.Boolean(string='Is Custom Plan', compute='_compute_plan_details')
    additional_stores = fields.Integer(string='Additional Stores Needed', default=0, help='Extra stores requested ($12 per additional store)')
    extra_store_price = fields.Float(string='Extra Price per Store ($)', compute='_compute_plan_details')
    computed_total_price = fields.Float(string='Total Monthly Price ($)', compute='_compute_total_price')

    @api.depends('subscription_plan_id')
    def _compute_plan_details(self):
        for wizard in self:
            if wizard.subscription_plan_id:
                wizard.is_custom = wizard.subscription_plan_id.is_custom
                wizard.extra_store_price = wizard.subscription_plan_id.extra_store_price
            else:
                wizard.is_custom = False
                wizard.extra_store_price = 12.0

    @api.depends('subscription_plan_id', 'subscription_plan_id.price', 'subscription_plan_id.is_custom', 'subscription_plan_id.extra_store_price', 'additional_stores')
    def _compute_total_price(self):
        for wizard in self:
            plan = wizard.subscription_plan_id
            if not plan:
                wizard.computed_total_price = 0.0
            elif plan.is_custom:
                extra = max(0, wizard.additional_stores or 0)
                wizard.computed_total_price = (plan.price or 0.0) + (extra * (plan.extra_store_price or 12.0))
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
            raise ValidationError('You cannot select your current subscription plan without changing store options.')
        
        extra_stores = max(0, self.additional_stores or 0) if self.subscription_plan_id.is_custom else 0
        if self.tenant_id.check_subscription_active():
            self.tenant_id.with_context(bypass_subscription_check=True).write({
                'pending_subscription_plan_id': self.subscription_plan_id.id,
                'pending_additional_stores': extra_stores,
            })
        else:
            self.tenant_id.with_context(bypass_subscription_check=True).write({
                'subscription_plan_id': self.subscription_plan_id.id,
                'additional_stores': extra_stores,
                'subscription_state': 'pending',
                'payment_status': 'unpaid'
            })
        return {
            'type': 'ir.actions.act_window_close'
        }



