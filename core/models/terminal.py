from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, RedirectWarning


class HavanoposdeskPosTerminal(models.Model):
    _name = 'havanoposdesk.pos.terminal'
    _description = 'POS Terminal'

    name = fields.Char(string='Terminal Name', required=True, readonly=True, default=lambda self: self._get_default_name())
    active = fields.Boolean(string='Active', default=True)
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
    device_hardware_id = fields.Char(string='Device Hardware ID', readonly=True)
    app_version = fields.Char(string='App Version', readonly=True)
    last_seen = fields.Datetime(string='Last Seen')
    sequence_prefix = fields.Char(string='Sequence Prefix')
    last_logged_in_user_id = fields.Many2one('res.users', string='Last Logged In By', readonly=True)
    taken_by_user_id = fields.Many2one('res.users', string='Taken By User')
    status = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('taken', 'Taken'),
        ('online', 'Online'),
        ('offline', 'Offline')
    ], string='Status', default='open')

    @api.model
    def _get_default_name(self):
        tenant_id = self.env.user.tenant_id.id
        if not tenant_id:
            tenant = self.env['havanoposdesk.tenant'].search([], limit=1)
            tenant_id = tenant.id if tenant else False
        
        if tenant_id:
            count = self.search_count([('tenant_id', '=', tenant_id)])
        else:
            count = self.search_count([])
        return f"Pos {count + 1}"

    def action_add_terminal(self):
        tenant_id = self.env.user.tenant_id.id
        if not tenant_id:
            tenant_id = (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        
        store_id = self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1).id
        if not store_id:
            store_id = self.env['havanoposdesk.store'].create({
                'name': self.env.user.tenant_id.name or 'Default Store',
                'tenant_id': tenant_id
            }).id

        count = self.search_count([('tenant_id', '=', tenant_id)])
        name = f"Pos {count + 1}"
        
        terminal = self.create({
            'name': name,
            'store_id': store_id,
            'tenant_id': tenant_id,
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.pos.terminal',
            'res_id': terminal.id,
            'view_mode': 'form',
            'target': 'current',
            'flags': {'initial_mode': 'edit'},
        }

    @api.model_create_multi
    def create(self, vals_list):
        import random
        import string
        for vals in vals_list:
            if not vals.get('sequence_prefix'):
                vals['sequence_prefix'] = ''.join(random.choices(string.ascii_uppercase, k=4))

            if self.env.user.havano_role == 'super_admin':
                continue
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if not tenant_id:
                raise ValidationError('Cannot create a terminal without an associated tenant.')
                
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
            if not tenant.check_subscription_active():
                plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
                if plan:
                    price = tenant.pending_subscription_total_amount if tenant.pending_subscription_plan_id else (tenant.subscription_total_amount or plan.price)
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
                                'default_subscription_plan_id': plan.id,
                                'default_amount': price,
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
                
            max_allowed = tenant.effective_max_terminals or (plan.max_terminals if plan else 0)
            if max_allowed and max_allowed > 0:
                current = self.search_count([('tenant_id', '=', tenant.id)])
                if current >= max_allowed:
                    raise RedirectWarning(
                        _('Maximum number of POS Terminals (%s) reached for this subscription plan.') % max_allowed,
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



    @api.model
    def _cron_check_terminal_status(self):
        from datetime import datetime, timedelta
        limit = datetime.now() - timedelta(minutes=2)
        inactive = self.search([
            ('status', '=', 'online'),
            '|',
            ('last_seen', '<', limit),
            ('last_seen', '=', False)
        ])
        if inactive:
            inactive.write({'status': 'offline'})
