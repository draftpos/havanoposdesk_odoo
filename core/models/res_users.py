from odoo import models, fields, api, tools, _
from odoo.exceptions import ValidationError, RedirectWarning
from odoo.tools import frozendict
import datetime

class ResUsers(models.Model):
    _inherit = "res.users"
    
    havano_role = fields.Selection([
        ('super_admin', 'Super Admin'),
        ('admin', 'Admin'),
        ('user', 'Cashier')
    ], string="Havano Role", default='user')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string="Tenant")
    saas_state = fields.Selection([
        ('unverified', 'Unverified'),
        ('verified', 'Verified'),
        ('suspended', 'Suspended')
    ], string="SaaS State", default='unverified')
    default_store_id = fields.Many2one('havanoposdesk.store', string="Default Store")
    store_ids = fields.Many2many('havanoposdesk.store', 'res_users_store_rel', 'user_id', 'store_id', string="Allowed Stores")
    selected_shop_id = fields.Many2one('havanoposdesk.store', string="Selected Shop")
    selected_terminal_id = fields.Many2one('havanoposdesk.pos.terminal', string="Selected Terminal")
    pin = fields.Char(string="PIN Code")
    user_rights_profile_id = fields.Many2one('havanoposdesk.user.rights.profile', string="User Rights Profile")
    allow_backoffice = fields.Boolean(string="Access Backoffice", compute="_compute_allow_backoffice", inverse="_inverse_allow_backoffice", store=True)
    has_password = fields.Boolean(string="Has Password", compute="_compute_has_password")

    def _compute_has_password(self):
        saved_users = self.filtered('id')
        (self - saved_users).has_password = False
        if saved_users:
            self.env.cr.execute("SELECT id, password FROM res_users WHERE id IN %s", [tuple(saved_users.ids)])
            passwords = {r[0]: bool(r[1]) for r in self.env.cr.fetchall()}
            for user in saved_users:
                user.has_password = passwords.get(user.id, False)

    @api.onchange('default_store_id')
    def _onchange_default_store_id(self):
        if self.default_store_id:
            self.store_ids = self.store_ids | self.default_store_id

    @api.depends('havano_role')
    def _compute_allow_backoffice(self):
        for user in self:
            user.allow_backoffice = (user.havano_role in ['admin', 'super_admin'])



    def _inverse_allow_backoffice(self):
        for user in self:
            if user.havano_role == 'super_admin':
                continue
            if user.allow_backoffice:
                user.havano_role = 'admin'
            else:
                user.havano_role = 'user'

    @api.constrains('password', 'allow_backoffice')
    def _check_backoffice_password(self):
        for user in self:
            if user.password and not user.allow_backoffice and user.havano_role == 'user':
                raise ValidationError(_("You cannot assign a backoffice password to a user who does not have 'Access Backoffice' enabled."))

    @api.constrains('pin', 'tenant_id')
    def _check_pin_uniqueness(self):
        for user in self:
            if user.pin and user.pin.strip():
                if len(user.pin.strip()) != 4 or not user.pin.strip().isdigit():
                    raise ValidationError(_("The POS Login PIN must be exactly 4 digits."))
                
                duplicate = self.search([
                    ('tenant_id', '=', user.tenant_id.id),
                    ('pin', '=', user.pin),
                    ('id', '!=', user.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("The PIN code must be unique per tenant! User '%s' already has this PIN.") % duplicate.name)

    @api.model
    def _get_default_action_id(self):
        action = self.env.ref('havanoposdesk_odoo.action_havano_dashboard_client', raise_if_not_found=False)
        return action.id if action else False

    action_id = fields.Many2one(default=_get_default_action_id)

    verification_token = fields.Char(string="Verification Token", copy=False)
    verification_sent_at = fields.Datetime(string="Verification Sent At", copy=False)

    api_company_name = fields.Char(string="API Company Name", default="Havano POS Company")
    api_currency = fields.Char(string="API Currency", default="USD")
    api_uom = fields.Char(string="API Default UOM", default="Nos")
    api_cost_center = fields.Char(string="API Cost Center")
    api_warehouse = fields.Char(string="API Warehouse")

    allow_discount = fields.Boolean(string="Allow Discount", default=True)
    max_discount_percent = fields.Float(string="Max Discount Percent", default=100.0)
    require_shift = fields.Boolean(string="Require Shift", default=False)

    @api.model
    def check_access_rights(self, operation, raise_exception=True):
        if self.env.user.havano_role == 'admin' and operation in ('read', 'write', 'create', 'search'):
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    @api.model_create_multi
    def create(self, vals_list):
        import uuid
        for vals in vals_list:
            if 'allow_backoffice' in vals:
                vals['havano_role'] = 'admin' if vals['allow_backoffice'] else 'user'
                
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if 'login' not in vals or not vals.get('login'):
                name = vals.get('name', 'user').lower().replace(' ', '')
                store_id = vals.get('default_store_id') or self.env.user.default_store_id.id
                store_domain = "havanopos.com"
                if store_id:
                    store = self.env['havanoposdesk.store'].sudo().browse(store_id)
                    if store:
                        store_domain = store.name.lower().replace(' ', '') + ".com"
                
                base_email = f"{name}@{store_domain}"
                email = base_email
                counter = 1
                while self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', email)]) > 0:
                    email = f"{name}{counter}@{store_domain}"
                    counter += 1
                vals['login'] = email
            else:
                email = vals.get('login')
                if self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', email)]) > 0:
                    raise ValidationError(_("Oops! Sorry, the email '%s' is already in use by another user.") % email)

            if vals.get('saas_state') == 'unverified' and not vals.get('verification_token'):
                vals['verification_token'] = str(uuid.uuid4())
                vals['verification_sent_at'] = fields.Datetime.now()

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
                    if tenant.subscription_plan_id:
                        raise RedirectWarning(
                            _('Cannot create a cashier. The tenant subscription is not active.'),
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
                            _('Cannot create a cashier. Please pick a subscription plan.'),
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
                        _('Please pick a subscription plan to start creating cashiers.'),
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
                    
                if plan.max_users and plan.max_users > 0:
                    current = self.search_count([('tenant_id', '=', tenant.id), ('havano_role', '=', 'user')])
                    if current >= plan.max_users:
                        raise RedirectWarning(
                            _('Maximum number of cashiers (%s) reached for this subscription plan.') % plan.max_users,
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

        # Handle delegated user creation by Tenant Admins
        if self.env.user.havano_role == 'admin':
            for vals in vals_list:
                vals['havano_role'] = 'user'
                vals['saas_state'] = 'verified'
                vals['tenant_id'] = self.env.user.tenant_id.id
                
                # Default User Settings: Cashier profile, 0% discount, default store
                vals['allow_discount'] = False
                vals['max_discount_percent'] = 0.0
                
                tenant_id = self.env.user.tenant_id.id
                default_store = self.env.user.default_store_id
                if not default_store:
                    default_store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id), ('is_default', '=', True)], limit=1)
                if not default_store:
                    default_store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1)
                
                if default_store:
                    vals['default_store_id'] = default_store.id
                    if 'store_ids' not in vals:
                        vals['store_ids'] = [(6, 0, [default_store.id])]
                    elif isinstance(vals['store_ids'], list):
                        vals['store_ids'].append((4, default_store.id, 0))
        
        # Pre-process group_ids to prevent mutual exclusivity errors on create
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        internal_group = self.env.ref('base.group_user', raise_if_not_found=False)
        tenant_admin_group = self.env.ref('havanoposdesk_odoo.group_tenant_admin', raise_if_not_found=False)
        erp_manager_group = self.env.ref('base.group_erp_manager', raise_if_not_found=False)
        group_system = self.env.ref('base.group_system', raise_if_not_found=False)

        for vals in vals_list:
            role = vals.get('havano_role')
            if role:
                # Remove portal group from incoming vals if it exists
                existing_groups = []
                if 'group_ids' in vals and isinstance(vals['group_ids'], list):
                    for cmd in vals['group_ids']:
                        if cmd[0] == 6:
                            # Filter out portal group
                            filtered_ids = [gid for gid in cmd[2] if portal_group and gid != portal_group.id]
                            existing_groups.append((6, 0, filtered_ids))
                        else:
                            existing_groups.append(cmd)
                else:
                    existing_groups = vals.get('group_ids', [])
                
                # Assign correct backend groups based on role
                if role == 'super_admin' and group_system:
                    existing_groups.append((4, group_system.id, 0))
                    existing_groups.append((4, internal_group.id, 0))
                elif role == 'admin' and tenant_admin_group and erp_manager_group:
                    existing_groups.append((4, tenant_admin_group.id, 0))
                    existing_groups.append((4, erp_manager_group.id, 0))
                    existing_groups.append((4, internal_group.id, 0))
                elif role == 'user' and internal_group:
                    existing_groups.append((4, internal_group.id, 0))
                
                vals['group_ids'] = existing_groups

        if self.env.user.havano_role == 'admin':
            users = super(ResUsers, self.sudo()).create(vals_list)
        else:
            users = super().create(vals_list)

        for user in users:
            if user.saas_state == 'unverified' and user.verification_token:
                user.sudo().send_verification_email()

        return users

    def write(self, vals):
        if 'allow_backoffice' in vals:
            vals['havano_role'] = 'admin' if vals['allow_backoffice'] else 'user'
            
        if 'login' in vals:
            email = vals.get('login')
            if email:
                for user in self:
                    if email != user.login and self.env['res.users'].sudo().with_context(active_test=False).search_count([('login', '=', email)]) > 0:
                        raise ValidationError(_("Oops! Sorry, the email '%s' is already in use by another user.") % email)

        if self.env.user.havano_role == 'admin':
            # Restrict Tenant Admins to modifying only cashiers in their own tenant
            for user in self:
                if user.tenant_id != self.env.user.tenant_id:
                    raise ValidationError('You can only modify users within your own tenant.')
            # Prevent self-promotion or tenant modifications
            vals.pop('tenant_id', None)
            vals.pop('havano_role', None)
            res = super(ResUsers, self.sudo()).write(vals)
        else:
            res = super().write(vals)

        if ('havano_role' in vals or 'group_ids' in vals) and not self.env.context.get('bypass_sync_role_groups'):
            tenant_admin_group = self.env.ref('havanoposdesk_odoo.group_tenant_admin', raise_if_not_found=False)
            erp_manager_group = self.env.ref('base.group_erp_manager', raise_if_not_found=False)
            group_system = self.env.ref('base.group_system', raise_if_not_found=False)
            for user in self:
                group_cmds = []
                portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
                public_group = self.env.ref('base.group_public', raise_if_not_found=False)
                if portal_group and portal_group in user.group_ids:
                    group_cmds.append((3, portal_group.id, 0))
                if public_group and public_group in user.group_ids:
                    group_cmds.append((3, public_group.id, 0))
                
                if group_cmds:
                    user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})

                if user.havano_role == 'super_admin':
                    if group_system and group_system not in user.group_ids:
                        user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': [(4, group_system.id, 0)]})
                elif user.havano_role == 'admin':
                    # Admin: ensure they have both Tenant Admin group and Settings group
                    group_cmds = []
                    if tenant_admin_group and tenant_admin_group not in user.group_ids:
                        group_cmds.append((4, tenant_admin_group.id, 0))
                    if erp_manager_group and erp_manager_group not in user.group_ids:
                        group_cmds.append((4, erp_manager_group.id, 0))
                    if group_cmds:
                        user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})
                else:
                    # Cashier/other: strip admin and settings groups
                    group_cmds = []
                    if tenant_admin_group and tenant_admin_group in user.group_ids:
                        group_cmds.append((3, tenant_admin_group.id, 0))
                    if erp_manager_group and erp_manager_group in user.group_ids:
                        group_cmds.append((3, erp_manager_group.id, 0))
                    if group_cmds:
                        user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})
        return res

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
        from odoo.http import request
        org_name = request.params.get('organization_name') if request else False
        tenant_name = org_name or f"{values.get('name', 'My')}'s Business"
        
        country_id = request.params.get('country_id') if request else False
        currency_id = False
        
        if country_id:
            country = self.env['res.country'].sudo().browse(int(country_id))
            if country.code == 'ZW':
                usd = self.env.ref('base.USD', raise_if_not_found=False)
                currency_id = usd.id if usd else False
            elif country.currency_id:
                currency_id = country.currency_id.id
                
        tenant_vals = {
            'name': tenant_name,
            'subscription_state': 'active',
        }
        if currency_id:
            tenant_vals['currency_id'] = currency_id
            
        # 1. Create a new Tenant record for the user's business
        tenant = self.env['havanoposdesk.tenant'].sudo().create(tenant_vals)

        # Process phone number if provided
        phone = False
        if request:
            phone_num = request.params.get('phone_number')
            country_code = request.params.get('country_code', '')
            if phone_num:
                phone = f"{country_code}{phone_num}"

        # 2. Inject SaaS values
        values.update({
            'tenant_id': tenant.id,
            'havano_role': 'admin',
            'saas_state': 'unverified',
        })
        if phone:
            values['phone'] = phone

        # 3. Create the user using standard portal template copy
        user = super()._create_user_from_template(values)

        return user

    def send_verification_email(self):
        self.ensure_one()
        if not self.verification_token:
            return
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        verification_url = f"{base_url}/web/verify_email?token={self.verification_token}"
        
        subject = _("Verify Your Havano POS Desk Account")
        body_html = f"""
            <div style="margin: 0; padding: 0; font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; background-color: #f8f9fa;">
                <table align="center" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 10px rgba(0,0,0,0.05); border: 1px solid #e9ecef;">
                    <tr>
                        <td align="center" style="padding: 40px 20px; background-color: #1a252f; color: #ffffff;">
                            <h2 style="margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 0.5px;">Havano POS Desk</h2>
                            <p style="margin: 5px 0 0 0; font-size: 14px; opacity: 0.8;">Unified SaaS POS Backend</p>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 40px 30px; color: #495057; line-height: 1.6; font-size: 16px;">
                            <p style="margin-top: 0;">Hello <strong>{self.name}</strong>,</p>
                            <p>Thank you for signing up with Havano POS Desk! To start using your account and prevent suspension, please verify your email address by clicking the button below:</p>
                            <div style="text-align: center; margin: 30px 0;">
                                <a href="{verification_url}" style="background-color: #007bff; color: #ffffff; text-decoration: none; padding: 12px 30px; font-size: 16px; font-weight: 500; border-radius: 5px; display: inline-block; transition: background-color 0.2s;">
                                    Verify Email Address
                                </a>
                            </div>
                            <p style="font-size: 14px; color: #6c757d;">Or copy and paste this link into your browser:</p>
                            <p style="font-size: 13px; color: #007bff; word-break: break-all; margin-bottom: 30px;">
                                <a href="{verification_url}" style="color: #007bff; text-decoration: underline;">{verification_url}</a>
                            </p>
                            <p style="margin-bottom: 0;">Best regards,<br/>The Havano Team</p>
                        </td>
                    </tr>
                    <tr>
                        <td align="center" style="padding: 20px; background-color: #f1f3f5; font-size: 12px; color: #6c757d; border-top: 1px solid #e9ecef;">
                            &copy; {datetime.datetime.now().year} Havano POS Desk. All rights reserved.
                        </td>
                    </tr>
                </table>
            </div>
        """
        
        mail_values = {
            'subject': subject,
            'body_html': body_html,
            'email_to': self.login,
            'email_from': self.company_id.email or 'noreply@havanopos.com',
        }
        self.env['mail.mail'].sudo().create(mail_values)

    def action_send_verification_email(self):
        for user in self:
            if user.saas_state == 'unverified':
                import uuid
                if not user.verification_token:
                    user.verification_token = str(uuid.uuid4())
                user.verification_sent_at = fields.Datetime.now()
                user.send_verification_email()

    @api.model
    def cron_check_unverified_users(self):
        ICPSudo = self.env['ir.config_parameter'].sudo()
        try:
            grace_number = int(ICPSudo.get_param('havanoposdesk.verification_grace_number', '24') or '24')
        except ValueError:
            grace_number = 24
        grace_unit = ICPSudo.get_param('havanoposdesk.verification_grace_unit', 'hours')
        
        from datetime import datetime, timedelta
        now = datetime.now()
        if grace_unit == 'days':
            threshold_time = now - timedelta(days=grace_number)
        else:
            threshold_time = now - timedelta(hours=grace_number)
            
        unverified_users = self.sudo().search([
            ('saas_state', '=', 'unverified'),
            ('active', '=', True),
            '|',
            ('verification_sent_at', '<', threshold_time),
            ('&', ('verification_sent_at', '=', False), ('create_date', '<', threshold_time))
        ])
        
        if unverified_users:
            unverified_users.action_suspend_user()


class HavanoChangePasswordWizard(models.TransientModel):
    _name = 'havano.change.password.wizard'
    _description = 'Change Cashier Password'

    user_id = fields.Many2one('res.users', string='Cashier', required=True)
    new_password = fields.Char(string='New Password', required=True)

    def action_change_password(self):
        self.ensure_one()
        if self.env.user.havano_role == 'admin' and self.user_id.tenant_id != self.env.user.tenant_id:
            raise ValidationError('You can only change password for cashiers in your own tenant.')
        self.user_id.sudo().write({'password': self.new_password})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Password changed successfully.',
                'type': 'success',
                'sticky': False,
            }
        }


class HavanoChangePinWizard(models.TransientModel):
    _name = 'havano.change.pin.wizard'
    _description = 'Change My PIN'

    new_pin = fields.Char(string='New PIN', required=True)

    def action_change_pin(self):
        self.ensure_one()
        pin = self.new_pin.strip() if self.new_pin else ''
        if not pin:
            raise ValidationError(_('PIN cannot be empty.'))
        if not pin.isdigit() or len(pin) != 4:
            raise ValidationError(_('PIN must be a 4-digit number.'))

        # Check uniqueness in the tenant
        duplicate = self.env['res.users'].search([
            ('tenant_id', '=', self.env.user.tenant_id.id),
            ('pin', '=', pin),
            ('id', '!=', self.env.user.id)
        ], limit=1)
        if duplicate:
            raise ValidationError(_("The PIN code must be unique per tenant! User '%s' already has this PIN.") % duplicate.name)

        self.env.user.sudo().write({'pin': pin})
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Success'),
                'message': _('PIN changed successfully.'),
                'type': 'success',
                'sticky': False,
            }
        }







