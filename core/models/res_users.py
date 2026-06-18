from odoo import models, fields, api, tools
from odoo.exceptions import ValidationError
from odoo.tools import frozendict

class ResUsers(models.Model):
    _inherit = "res.users"
    
    havano_role = fields.Selection([
        ('super_admin', 'Super Admin'),
        ('admin', 'Tenant Admin'),
        ('user', 'User/Cashier')
    ], string="Havano Role", default='user')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string="Tenant")
    saas_state = fields.Selection([
        ('unverified', 'Unverified'),
        ('verified', 'Verified'),
        ('suspended', 'Suspended')
    ], string="SaaS State", default='unverified')
    default_store_id = fields.Many2one('havanoposdesk.store', string="Default Store")
    store_ids = fields.Many2many('havanoposdesk.store', 'res_users_store_rel', 'user_id', 'store_id', string="Allowed Stores")

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        if self.env.user.havano_role == 'admin' and operation in ('read', 'write', 'create', 'search'):
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if self.env.user.havano_role == 'super_admin':
                continue
                
            # If creating a cashier ('user')
            role = vals.get('havano_role')
            if role == 'user' or (not role and self.env.user.havano_role == 'admin'):
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                if not tenant_id:
                    continue
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant.subscription_state != 'active':
                    raise ValidationError('Cannot create a cashier. The tenant subscription is not active.')
                    
                plan = tenant.subscription_plan_id
                if not plan:
                    raise ValidationError('Please pick a subscription plan to start creating cashiers.')
                    
                if plan.max_users and plan.max_users > 0:
                    current = self.search_count([('tenant_id', '=', tenant.id), ('havano_role', '=', 'user')])
                    if current >= plan.max_users:
                        raise ValidationError(f'Maximum number of cashiers ({plan.max_users}) reached for this subscription plan.')

        # Handle delegated user creation by Tenant Admins
        if self.env.user.havano_role == 'admin':
            for vals in vals_list:
                vals['havano_role'] = 'user'
                vals['saas_state'] = 'verified'
                vals['tenant_id'] = self.env.user.tenant_id.id
                internal_group = self.env.ref('base.group_user')
                vals['group_ids'] = [(4, internal_group.id, 0)]
            return super(ResUsers, self.sudo()).create(vals_list)

        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.havano_role == 'admin':
            # Restrict Tenant Admins to modifying only cashiers in their own tenant
            for user in self:
                if user.tenant_id != self.env.user.tenant_id:
                    raise ValidationError('You can only modify users within your own tenant.')
            # Prevent self-promotion or tenant modifications
            vals.pop('tenant_id', None)
            vals.pop('havano_role', None)
            return super(ResUsers, self.sudo()).write(vals)

        return super().write(vals)

    def action_verify_user(self):
        for user in self:
            user.write({
                'saas_state': 'verified',
                'active': True
            })

    def action_suspend_user(self):
        for user in self:
            if user.id == self.env.user.id or user.id == 2:
                continue
            user.write({
                'saas_state': 'suspended',
                'active': False
            })

    @api.model
    @tools.ormcache('self.env.uid')
    def context_get(self):
        context = super().context_get()
        ctx = dict(context)
        ctx['tenant_id'] = self.env.user.tenant_id.id
        return frozendict(ctx)

    @api.model
    def _get_invalidation_fields(self):
        return super()._get_invalidation_fields() | {'tenant_id'}

    def _create_user_from_template(self, values):
        # 1. Create a new Tenant record for the user's business
        tenant_name = f"{values.get('name', 'My')}'s Business"
        tenant = self.env['havanoposdesk.tenant'].sudo().create({
            'name': tenant_name,
            'subscription_state': 'active',
        })

        # 2. Inject SaaS values
        values.update({
            'tenant_id': tenant.id,
            'havano_role': 'admin',
            'saas_state': 'verified',
        })

        # 3. Create the user using standard portal template copy
        user = super()._create_user_from_template(values)

        # 4. Swap Portal group for Internal User group to give access to backend
        portal_group = self.env.ref('base.group_portal')
        internal_group = self.env.ref('base.group_user')

        user.sudo().write({
            'group_ids': [
                (3, portal_group.id, 0),    # Unlink portal
                (4, internal_group.id, 0),  # Link internal
            ]
        })

        return user


