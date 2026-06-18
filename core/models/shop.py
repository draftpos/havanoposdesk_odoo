from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HavanoposdeskShop(models.Model):
    _name = 'havanoposdesk.shop'
    _description = 'Shop/Store'

    name = fields.Char(string='Shop Name', required=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    active = fields.Boolean(string='Active', default=True)

<<<<<<< HEAD
    # Computed Metrics
    terminal_count = fields.Integer(string='Terminals', compute='_compute_shop_metrics')
    last_open = fields.Datetime(string='Last Open', compute='_compute_shop_metrics')
    sales_count = fields.Integer(string='Sales Count', compute='_compute_shop_metrics')
    purchases_count = fields.Integer(string='Purchases Count', compute='_compute_shop_metrics')
    sale_value = fields.Float(string='Sale Value', compute='_compute_shop_metrics')
    users_count = fields.Integer(string='Users', compute='_compute_shop_metrics')

    def _compute_shop_metrics(self):
        for shop in self:
            # Terminals count
            shop.terminal_count = self.env['havanoposdesk.pos.terminal'].sudo().search_count([('shop_id', '=', shop.id)])
            
            # Sales metrics
            sales = self.env['havanoposdesk.sale'].sudo().search([('shop_id', '=', shop.id)])
            shop.sales_count = len(sales)
            shop.sale_value = sum(sales.mapped('amount_total'))
            
            # Purchases metrics
            purchases = self.env['havanoposdesk.purchase'].sudo().search([('shop_id', '=', shop.id)])
            shop.purchases_count = len(purchases)
            
            # Assigned users/cashiers count
            users = self.env['res.users'].sudo().search([
                '|', 
                ('default_shop_id', '=', shop.id), 
                ('shop_ids', 'in', shop.id)
            ])
            shop.users_count = len(users)
            
            # Last Open (calculated based on latest sale, purchase, or user login)
            dates = []
            if sales:
                dates.extend(d for d in sales.mapped('date') if d)
            if purchases:
                dates.extend(d for d in purchases.mapped('date') if d)
            dates.extend(u.login_date for u in users if u.login_date)
            
            shop.last_open = max(dates) if dates else False

=======
>>>>>>> 4b8e381 (feat:updated)
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a shop without an associated tenant.')
                
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if tenant.subscription_state != 'active':
                raise ValidationError('Cannot create a shop. The tenant subscription is not active.')
                
            plan = tenant.subscription_plan_id
            if not plan:
                raise ValidationError('Please pick a subscription plan to start creating shops.')
                
            if plan.max_shops and plan.max_shops > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= plan.max_shops:
                    raise ValidationError(f'Maximum number of shops ({plan.max_shops}) reached for this subscription plan.')
                    
            # Ensure the tenant_id is correctly forced
            vals['tenant_id'] = tenant_id

        return super().create(vals_list)


<<<<<<< HEAD

=======
>>>>>>> 4b8e381 (feat:updated)
