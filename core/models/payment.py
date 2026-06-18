from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.addons.havano_payments.models.paynow_client import PaynowClient

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


class HavanoposdeskSubscriptionPayWizard(models.TransientModel):
    _name = 'havanoposdesk.subscription.pay.wizard'
    _description = 'Pay Subscription Wizard'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', required=True)
    amount = fields.Float(string='Amount to Pay', required=True)
    payment_method = fields.Selection([
        ('paynow', 'Paynow Card (Redirection)'),
        ('ecocash', 'EcoCash Mobile Prompt (Zimbabwe)')
    ], string='Payment Method', default='paynow', required=True)
    phone = fields.Char(string='EcoCash Phone Number', help="Enter number starting with 077... or 078...")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            tenant = self.env['havanoposdesk.tenant'].browse(active_id)
            res.update({
                'tenant_id': tenant.id,
                'subscription_plan_id': tenant.subscription_plan_id.id,
                'amount': tenant.subscription_plan_id.price,
            })
        return res

    def action_pay(self):
        self.ensure_one()
        provider = self.env['payment.provider'].sudo().search([('code', '=', 'havano_payments')], limit=1)
        if not provider:
            raise ValidationError('Havano Payments provider is not configured. Please configure it in SaaS Config.')

        import time
        reference = f"SUB-{self.tenant_id.id}-{self.subscription_plan_id.id}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"

        subscription_payment = self.env['havanoposdesk.subscription.payment'].create({
            'tenant_id': self.tenant_id.id,
            'subscription_plan_id': self.subscription_plan_id.id,
            'amount': self.amount,
            'payment_method': self.payment_method,
            'transaction_reference': reference,
            'state': 'pending',
        })

        payment_method_rec = self.env['payment.method'].sudo().search([('code', '=', self.payment_method)], limit=1)

        tx = self.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method_rec.id if payment_method_rec else False,
            'amount': self.amount,
            'currency_id': self.env.company.currency_id.id or self.env['res.currency'].search([('name', '=', 'USD')], limit=1).id,
            'reference': reference,
            'partner_id': self.env.user.partner_id.id,
            'operation': 'online_redirect',
            'subscription_payment_id': subscription_payment.id,
        })

        base_url = provider.get_base_url()
        result_url = f"{base_url}/payment/havano_payments/webhook?reference={reference}"

        if self.payment_method == 'ecocash':
            if not self.phone:
                raise ValidationError('Please enter your EcoCash phone number.')
            client = PaynowClient(provider.paynow_integration_id, provider.paynow_integration_key)
            mobile_res = client.initiate_mobile_transaction(
                reference=reference,
                amount=self.amount,
                authemail=self.env.user.email or "customer@example.com",
                phone=self.phone,
                method="ecocash",
                result_url=result_url,
                additional_info=f"Subscription for {self.tenant_id.name}"
            )
            if not mobile_res.get('success'):
                tx._set_error(mobile_res.get('error'))
                raise ValidationError(f"EcoCash initiation failed: {mobile_res.get('error')}")
            
            tx.paynow_poll_url = mobile_res['pollurl']
            tx._set_pending()

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'EcoCash Payment Initiated',
                    'message': mobile_res.get('instructions') or 'A prompt was sent to your phone. Please enter your PIN to complete the payment.',
                    'type': 'success',
                    'sticky': True,
                    'next': {'type': 'ir.actions.act_window_close'},
                }
            }
        else:
            return_url = f"{base_url}/payment/havano_payments/return?reference={reference}"
            client = PaynowClient(provider.paynow_integration_id, provider.paynow_integration_key)
            init_res = client.initiate_transaction(
                reference=reference,
                amount=self.amount,
                authemail=self.env.user.email or "customer@example.com",
                return_url=return_url,
                result_url=result_url,
                additional_info=f"Subscription for {self.tenant_id.name}"
            )
            if not init_res.get('success'):
                tx._set_error(init_res.get('error'))
                raise ValidationError(f"Paynow initiation failed: {init_res.get('error')}")
            
            tx.paynow_poll_url = init_res['pollurl']
            tx._set_pending()

            return {
                'type': 'ir.actions.act_url',
                'url': init_res['browserurl'],
                'target': 'self',
            }
