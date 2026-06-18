from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning


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
                if tenant.subscription_plan_id:
                    raise RedirectWarning(
                        _('Cannot create a POS Terminal. The tenant subscription is not active.'),
                        {
                            'name': _('Pay & Activate Subscription'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.subscription.pay.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                                'default_subscription_plan_id': tenant.subscription_plan_id.id,
                                'default_amount': tenant.subscription_plan_id.price,
                            }
                        },
                        _('Subscribe Now')
                    )
                else:
                    raise RedirectWarning(
                        _('Cannot create a POS Terminal. Please pick a subscription plan.'),
                        {
                            'name': _('Select Subscription Plan'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                            }
                        },
                        _('Select Plan')
                    )
                
            plan = tenant.subscription_plan_id
            if not plan:
                raise RedirectWarning(
                    _('Please pick a subscription plan to start creating POS Terminals.'),
                    {
                        'name': _('Select Subscription Plan'),
                        'type': 'ir.actions.act_window',
                        'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                        'view_mode': 'form',
                        'views': [(False, 'form')],
                        'target': 'new',
                        'context': {
                            'default_tenant_id': tenant.id,
                        }
                    },
                    _('Select Plan')
                )
                
            if plan.max_terminals and plan.max_terminals > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= plan.max_terminals:
                    raise RedirectWarning(
                        _('Maximum number of POS Terminals (%s) reached for this subscription plan.') % plan.max_terminals,
                        {
                            'name': _('Select Subscription Plan'),
                            'type': 'ir.actions.act_window',
                            'res_model': 'havanoposdesk.tenant.upgrade.wizard',
                            'view_mode': 'form',
                            'views': [(False, 'form')],
                            'target': 'new',
                            'context': {
                                'default_tenant_id': tenant.id,
                            }
                        },
                        _('Upgrade Subscription')
                    )
                    
            # Ensure the tenant_id is correctly forced
            vals['tenant_id'] = tenant_id

        return super().create(vals_list)

