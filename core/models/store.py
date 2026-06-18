from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HavanoposdeskStore(models.Model):
    _name = 'havanoposdesk.store'
    _description = 'Store'

    name = fields.Char(string='Store Name', required=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    active = fields.Boolean(string='Active', default=True)
    is_default = fields.Boolean(string='Is Default', default=False)

    @api.constrains('is_default', 'tenant_id')
    def _check_single_default_store(self):
        for store in self:
            if store.is_default:
                domain = [
                    ('tenant_id', '=', store.tenant_id.id),
                    ('is_default', '=', True),
                    ('id', '!=', store.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError("Only one store can be set as the default store per tenant.")

    # Computed statistics fields to avoid undefined errors in list view
    terminal_count = fields.Integer(string='Terminals', compute='_compute_store_statistics')
    last_open = fields.Date(string='Last Open', compute='_compute_store_statistics')
    sales_count = fields.Integer(string='Sales Count', compute='_compute_store_statistics')
    purchases_count = fields.Integer(string='Purchases Count', compute='_compute_store_statistics')
    sale_value = fields.Float(string='Sales Value', compute='_compute_store_statistics')
    users_count = fields.Integer(string='Users Count', compute='_compute_store_statistics')

    def _compute_store_statistics(self):
        for store in self:
            # Terminals
            terminals = self.env['havanoposdesk.pos.terminal'].search([('store_id', '=', store.id)])
            store.terminal_count = len(terminals)
            
            # Users
            store.users_count = self.env['res.users'].search_count([('store_ids', 'in', store.id)])
            
            # Sales & Purchases (using store name string)
            sales = self.env['havanoposdesk.sale'].search([('store', '=', store.name)])
            store.sales_count = len(sales)
            store.sale_value = sum(sales.mapped('line_ids.amount'))
            
            purchases = self.env['havanoposdesk.purchase'].search([('store', '=', store.name)])
            store.purchases_count = len(purchases)
            
            # Last open (from last sale date)
            if sales:
                last_sale = max(sales, key=lambda s: s.posting_date)
                store.last_open = last_sale.posting_date
            else:
                store.last_open = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a store without an associated tenant.')
                
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if tenant.subscription_state != 'active':
                raise ValidationError('Cannot create a store. The tenant subscription is not active.')
                
            plan = tenant.subscription_plan_id
            if not plan:
                raise ValidationError('Please pick a subscription plan to start creating stores.')
                
            if plan.max_stores and plan.max_stores > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= plan.max_stores:
                    raise ValidationError(f'Maximum number of stores ({plan.max_stores}) reached for this subscription plan.')
                    
            # Ensure the tenant_id is correctly forced
            vals['tenant_id'] = tenant_id

        return super().create(vals_list)


