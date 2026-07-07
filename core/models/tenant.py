from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

class HavanoposdeskTenant(models.Model):
    _name = 'havanoposdesk.tenant'
    _description = 'Havano POS Desk Tenant'

    name = fields.Char(string='Tenant Name', required=True)
    active = fields.Boolean(default=True)
    currency_id = fields.Many2one('res.currency', string='Default Currency', default=lambda self: self.env.ref('base.USD').id)
    allow_multi_currency = fields.Boolean(string='Allow Multi Currency', default=False)
    allow_advanced_pricing = fields.Boolean(string='Allow Advanced Pricing & Multi-UOM', default=False)
    
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan')
    subscription_state = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Payment'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled')
    ], string='Subscription State', default='active')
    subscription_start_date = fields.Date(string='Subscription Start Date')
    subscription_end_date = fields.Date(string='Subscription End Date')
    payment_status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('pending', 'Pending Payment'),
        ('paid', 'Paid')
    ], string='Payment Status', default='unpaid')
    
    user_ids = fields.One2many('res.users', 'tenant_id', string='Users')

    api_company_name = fields.Char(string="API Company Name", default="Havano POS Company")
    api_currency = fields.Char(string="API Currency", default="USD")
    # Products Sequence Config
    prod_seq_prefix = fields.Char(string='Product Sequence Prefix', default='')
    prod_seq_next = fields.Integer(string='Product Sequence Next Number', default=101)
    prod_seq_padding = fields.Integer(string='Product Sequence Padding', default=0)

    # Stock Adjustments Sequence Config
    stock_adj_seq_prefix = fields.Char(string='Stock Adjustment Sequence Prefix', default='')
    stock_adj_seq_next = fields.Integer(string='Stock Adjustment Sequence Next Number', default=1)
    stock_adj_seq_padding = fields.Integer(string='Stock Adjustment Sequence Padding', default=5)

    # Sales Sequence Config
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
    api_cost_center = fields.Char(string="API Cost Center")
    api_warehouse = fields.Char(string="API Warehouse")

    # SaaS backoffice-controlled toggles
    enable_quotations = fields.Boolean(string='Enable Quotations', default=False)
    enable_uom_conversion = fields.Boolean(string='Enable UOM Conversion', default=False)
    enable_payment_entries = fields.Boolean(string='Enable Payment Entries', default=False)
    show_qty_on_hand = fields.Boolean(string='Show Qty on Hand in POS', default=False)
    enable_shift = fields.Boolean(string='Enable Shift Management', default=False)
    enable_tax = fields.Boolean(string='Enable Tax', default=False)
    allow_negative_stock = fields.Boolean(string='Allow Negative Stock', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        tenants = super().create(vals_list)
        for tenant in tenants:
            tenant._seed_default_data()
        return tenants

    def _seed_default_data(self):
        self.ensure_one()
        # 1. Customer Group
        cg = self.env['havanoposdesk.customer.group'].sudo().create({'name': 'Default Group', 'tenant_id': self.id})
        # 2. Supplier
        self.env['havanoposdesk.supplier'].sudo().create({'name': 'general', 'tenant_id': self.id})
        # 3. Default Deposit Account
        self.env['havanoposdesk.account'].sudo().create({'name': 'cash', 'type': 'Cash', 'tenant_id': self.id})
        # 4. Default Expenses Account
        expenses = ['Electricity', 'Rent', 'Utilities', 'Wages & Salaries', 'Breakages', 'Council Licenses', 'Maintanences', 'Fuel']
        for exp in expenses:
            self.env['havanoposdesk.account'].sudo().create({'name': exp, 'type': 'Expense', 'tenant_id': self.id})
        # 5. Default Customer
        self.env['havanoposdesk.customer'].sudo().create({'name': 'cash customer', 'customer_group_id': cg.id, 'tenant_id': self.id})
        # 6. Default Categories
        self.env['havanoposdesk.category'].sudo().create({'name': 'Basic', 'tenant_id': self.id})
        self.env['havanoposdesk.category'].sudo().create({'name': 'Beveragies', 'tenant_id': self.id})
        # 7. Default Pricelist
        self.env['havanoposdesk.pricelist'].sudo().create({'name': 'Retail', 'type': 'selling', 'tenant_id': self.id})

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



