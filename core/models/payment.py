from odoo import models, fields

class HavanoposdeskSubscriptionPayment(models.Model):
    _name = 'havanoposdesk.subscription.payment'
    _description = 'Subscription Payment Transaction Log'
    _order = 'date desc, id desc'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', required=True)
    amount = fields.Float(string='Amount Paid', required=True)
    payment_method = fields.Char(string='Payment Method')
    transaction_reference = fields.Char(string='Transaction Reference')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('done', 'Done'),
        ('failed', 'Failed')
    ], string='Status', default='draft', required=True)
    date = fields.Datetime(string='Payment Date', default=fields.Datetime.now, required=True)
