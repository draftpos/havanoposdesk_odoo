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
            tenant.write({
                'subscription_state': 'active',
                'payment_status': 'paid',
                'active': True
            })

    def action_expire(self):
        for tenant in self:
            tenant.write({
                'subscription_state': 'expired'
            })

    def action_cancel(self):
        for tenant in self:
            tenant.write({
                'subscription_state': 'cancelled'
            })

    def action_select_plan(self, plan_id):
        self.write({
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
            tenant.write({
                'payment_status': 'paid',
                'subscription_state': 'active',
                'subscription_start_date': start_date,
                'subscription_end_date': end_date,
                'active': True
            })

