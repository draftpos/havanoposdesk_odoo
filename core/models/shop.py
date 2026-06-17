from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HavanoposdeskShop(models.Model):
    _name = 'havanoposdesk.shop'
    _description = 'Shop/Store'

    name = fields.Char(string='Shop Name', required=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    active = fields.Boolean(string='Active', default=True)

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


