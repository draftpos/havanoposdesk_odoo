from odoo import models, fields, api
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta

class HavanoposdeskTenant(models.Model):
    _name = 'havanoposdesk.tenant'
    _description = 'Havano POS Desk Tenant'

    name = fields.Char(string='Tenant Name', required=True)
    active = fields.Boolean(default=True)
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

    def action_approve(self):
        for tenant in self:
<<<<<<< HEAD
            tenant.with_context(bypass_subscription_check=True).write({
=======
            tenant.write({
>>>>>>> 4b8e381 (feat:updated)
                'subscription_state': 'active',
                'payment_status': 'paid',
                'active': True
            })

    def action_expire(self):
        for tenant in self:
<<<<<<< HEAD
            tenant.with_context(bypass_subscription_check=True).write({
=======
            tenant.write({
>>>>>>> 4b8e381 (feat:updated)
                'subscription_state': 'expired'
            })

    def action_cancel(self):
        for tenant in self:
<<<<<<< HEAD
            tenant.with_context(bypass_subscription_check=True).write({
=======
            tenant.write({
>>>>>>> 4b8e381 (feat:updated)
                'subscription_state': 'cancelled'
            })

    def action_select_plan(self, plan_id):
<<<<<<< HEAD
        self.with_context(bypass_subscription_check=True).write({
=======
        self.write({
>>>>>>> 4b8e381 (feat:updated)
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
<<<<<<< HEAD
            tenant.with_context(bypass_subscription_check=True).write({
=======
            tenant.write({
>>>>>>> 4b8e381 (feat:updated)
                'payment_status': 'paid',
                'subscription_state': 'active',
                'subscription_start_date': start_date,
                'subscription_end_date': end_date,
                'active': True
            })

<<<<<<< HEAD
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
                'default_subscription_plan_id': self.subscription_plan_id.id,
            }
        }

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

    def action_confirm(self):
        self.ensure_one()
        if not self.tenant_id:
            raise ValidationError('No tenant associated with the user.')
        self.tenant_id.with_context(bypass_subscription_check=True).write({
            'subscription_plan_id': self.subscription_plan_id.id,
            'subscription_state': 'pending',
            'payment_status': 'unpaid'
        })
        return {
            'type': 'ir.actions.act_window_close'
        }



=======
>>>>>>> 4b8e381 (feat:updated)
