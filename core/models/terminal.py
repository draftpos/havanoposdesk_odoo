from odoo import models, fields, api
from odoo.exceptions import ValidationError

class HavanoposdeskPosTerminal(models.Model):
    _name = 'havanoposdesk.pos.terminal'
    _description = 'POS Terminal'

    name = fields.Char(string='Terminal Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one(
        'havanoposdesk.store', 
        string='Store', 
        required=True, 
        default=lambda self: self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1).id
    )
    user_id = fields.Many2one('res.users', string='Assigned Cashier')
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline')
    ], string='Status', default='offline')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a terminal without an associated tenant.')
                
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if tenant.subscription_state != 'active':
                raise ValidationError('Cannot create a POS Terminal. The tenant subscription is not active.')
                
            plan = tenant.subscription_plan_id
            if not plan:
                raise ValidationError('Please pick a subscription plan to start creating POS Terminals.')
                
            if plan.max_terminals and plan.max_terminals > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= plan.max_terminals:
                    raise ValidationError(f'Maximum number of POS Terminals ({plan.max_terminals}) reached for this subscription plan.')
                    
            # Ensure the tenant_id is correctly forced
            vals['tenant_id'] = tenant_id

        return super().create(vals_list)

