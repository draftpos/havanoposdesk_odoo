from odoo import models, fields, api, tools, _
from odoo.exceptions import ValidationError, RedirectWarning
from odoo.tools import frozendict
import datetime

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

    verification_token = fields.Char(string="Verification Token", copy=False)
    verification_sent_at = fields.Datetime(string="Verification Sent At", copy=False)

    api_company_name = fields.Char(string="API Company Name", default="Havano POS Company")
    api_currency = fields.Char(string="API Currency", default="USD")
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
                internal_group = self.env.ref('base.group_user')
                vals['group_ids'] = [(4, internal_group.id, 0)]
            users = super(ResUsers, self.sudo()).create(vals_list)
        else:
            users = super().create(vals_list)

        for user in users:
            if user.saas_state == 'unverified' and user.verification_token:
                user.sudo().send_verification_email()

        return users

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
            'saas_state': 'unverified',
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
        self.env['mail.mail'].sudo().create(mail_values).send()

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


