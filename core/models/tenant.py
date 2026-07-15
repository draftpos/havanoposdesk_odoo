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
    allow_advanced_pricing = fields.Boolean(string='Allow Advanced Pricing & Multi-UOM', default=True)
    
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan')
    subscription_state = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Payment'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Subscription State', default='active')
    subscription_start_date = fields.Date(string='Subscription Start Date')
    subscription_end_date = fields.Date(string='Subscription End Date')
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

    api_company_name = fields.Char(string="API Company Name", default="Havano POS Company")
    api_currency = fields.Char(string="API Currency", default="USD")
    api_uom = fields.Char(string="API Default UOM", default="Nos")
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
                plan = self.env['havanoposdesk.subscription.plan'].sudo().search([], order='id asc', limit=1)
                if not plan:
                    plan = self.env['havanoposdesk.subscription.plan'].sudo().create({
                        'name': 'Default Plan',
                        'price': 0.0,
                        'max_users': 2,
                        'max_stores': 1,
                        'max_terminals': 2
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
                'name': 'Main Terminal',
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
        _logger.info("SEED_DEFAULT_DATA CALLED VIA RAW SQL FOR PERFORMANCE")
        store = self.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', self.id)], limit=1)
        store_id = store.id if store else None
        tenant_id = self.id
        uid = self.env.uid or 1
        now = fields.Datetime.now()
        
        # 1. Customer Group (need ID for Customer)
        self.env.cr.execute("""
            INSERT INTO havanoposdesk_customer_group (name, tenant_id, create_uid, write_uid, create_date, write_date)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id;
        """, ('Default Group', tenant_id, uid, uid, now, now))
        cg_id = self.env.cr.fetchone()[0]
        
        queries = []
        params = []
        
        # 2. Supplier
        queries.append("""INSERT INTO havanoposdesk_supplier (name, tenant_id, store_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s, %s)""")
        params.append(('General Supplier', tenant_id, store_id, uid, uid, now, now))
        
        # 3. Default Deposit Account
        queries.append("""INSERT INTO havanoposdesk_account (name, type, tenant_id, currency_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""")
        params.append(('Cash', 'Cash', tenant_id, self.currency_id.id if self.currency_id else None, uid, uid, now, now))
        
        # 4. Default Expenses Account
        expenses = ['Electricity', 'Rent', 'Utilities', 'Wages & Salaries', 'Breakages', 'Council Licenses', 'Maintanences', 'Fuel']
        for exp in expenses:
            queries.append("""INSERT INTO havanoposdesk_account (name, type, tenant_id, currency_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""")
            params.append((exp, 'Expense', tenant_id, self.currency_id.id if self.currency_id else None, uid, uid, now, now))
            
        # 5. Default Customer
        queries.append("""INSERT INTO havanoposdesk_customer (name, customer_group_id, tenant_id, store_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""")
        params.append(('Cash Customer', cg_id, tenant_id, store_id, uid, uid, now, now))
        
        # 6. Default Categories
        queries.append("""INSERT INTO havanoposdesk_category (name, tenant_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s)""")
        params.append(('Basic', tenant_id, uid, uid, now, now))
        queries.append("""INSERT INTO havanoposdesk_category (name, tenant_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s)""")
        params.append(('Beveragies', tenant_id, uid, uid, now, now))
        
        # 7. Default Pricelist
        queries.append("""INSERT INTO havanoposdesk_pricelist (name, type, tenant_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s, %s)""")
        params.append(('Retail', 'selling', tenant_id, uid, uid, now, now))
        
        # 8. Default UOMs
        uoms = ['Kg', 'Litre', 'Meter', 'Pieces', 'Box', 'Set']
        for uom in uoms:
            queries.append("""INSERT INTO havanoposdesk_uom (name, tenant_id, create_uid, write_uid, create_date, write_date) VALUES (%s, %s, %s, %s, %s, %s)""")
            params.append((uom, tenant_id, uid, uid, now, now))
        
        # 9. Default Taxes — seeded as INACTIVE so tenant manually activates what they need
        default_taxes = [
            ('VAT 15%',     15.0, 'Sales'),
            ('VAT 14.5%',   14.5, 'Sales'),
            ('VAT 10%',     10.0, 'Sales'),
            ('VAT 5%',       5.0, 'Sales'),
            ('Tourism Levy 2%', 2.0, 'Sales'),
            ('Service Charge 10%', 10.0, 'Sales'),
        ]
        for (tax_name, tax_rate, tax_type) in default_taxes:
            queries.append("""
                INSERT INTO havanoposdesk_tax (name, rate, tax_type, active, tenant_id, create_uid, write_uid, create_date, write_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """)
            params.append((tax_name, tax_rate, tax_type, False, tenant_id, uid, uid, now, now))
        
        # Execute all inserts in a single rapid batch
        for i, query in enumerate(queries):
            self.env.cr.execute(query, params[i])

    def action_approve(self):
        for tenant in self:
            tenant.with_context(bypass_subscription_check=True).write({
                'subscription_state': 'active',
                'payment_status': 'paid',
                'active': True
            })

    def action_expire(self):
        for tenant in self:
            tenant.with_context(bypass_subscription_check=True).write({
                'subscription_state': 'expired'
            })

    def action_cancel(self):
        for tenant in self:
            tenant.with_context(bypass_subscription_check=True).write({
                'subscription_state': 'cancelled'
            })

    def action_select_plan(self, plan_id):
        self.with_context(bypass_subscription_check=True).write({
            'subscription_plan_id': plan_id,
            'subscription_state': 'pending',
            'payment_status': 'unpaid'
        })

    def action_pay_and_activate(self):
        for tenant in self:
            plan = tenant.subscription_plan_id
            if not plan:
                raise ValidationError('No subscription plan selected.')
            duration = plan.duration_days or 30
            start_date = fields.Date.context_today(self)
            end_date = start_date + relativedelta(days=duration)
            tenant.with_context(bypass_subscription_check=True).write({
                'payment_status': 'paid',
                'subscription_state': 'active',
                'subscription_start_date': start_date,
                'subscription_end_date': end_date,
                'active': True
            })

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
        return {
            'name': 'Pay & Activate Subscription',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.subscription.pay.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_tenant_id': self.id,
                'default_subscription_plan_id': self.subscription_plan_id.id,
                'default_amount': self.subscription_plan_id.price,
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
        restricted_fields = {'payment_status', 'subscription_state', 'subscription_start_date', 'subscription_end_date', 'subscription_plan_id'}
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

    @api.onchange('tenant_id')
    def _onchange_tenant_id(self):
        if self.tenant_id and self.tenant_id.subscription_plan_id:
            return {'domain': {'subscription_plan_id': [('id', '!=', self.tenant_id.subscription_plan_id.id)]}}
        return {'domain': {'subscription_plan_id': []}}

    def action_confirm(self):
        self.ensure_one()
        if not self.tenant_id:
            raise ValidationError('No tenant associated with the user.')
        if self.subscription_plan_id == self.tenant_id.subscription_plan_id:
            raise ValidationError('You cannot select your current subscription plan. Please select a different plan to upgrade or downgrade.')
        self.tenant_id.with_context(bypass_subscription_check=True).write({
            'subscription_plan_id': self.subscription_plan_id.id,
            'subscription_state': 'pending',
            'payment_status': 'unpaid'
        })
        return {
            'type': 'ir.actions.act_window_close'
        }



