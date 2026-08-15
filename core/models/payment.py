from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from odoo.addons.havano_payments.models.paynow_client import PaynowClient

class HavanoposdeskSubscriptionPayment(models.Model):
    _name = 'havanoposdesk.subscription.payment'
    _description = 'Subscription Payment Transaction Log'
    _order = 'date desc, id desc'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', required=False)
    payment_type = fields.Selection([
        ('subscription', 'Subscription Plan Payment'),
        ('topup', 'Account Balance Top-Up')
    ], string='Payment Type', default='subscription', required=True)
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

    def action_approve(self):
        for pay in self:
            if pay.state != 'done':
                is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su
                if not is_super:
                    raise ValidationError('Only Super Admins can approve balance top-ups.')
                if pay.payment_type == 'topup':
                    new_balance = pay.tenant_id.account_balance + pay.amount
                    pay.tenant_id.with_context(bypass_subscription_check=True).write({'account_balance': new_balance})
                pay.write({'state': 'done'})

    def action_reject(self):
        for pay in self:
            is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su
            if not is_super:
                raise ValidationError('Only Super Admins can reject balance top-ups.')
            pay.write({'state': 'failed'})


class HavanoposdeskSubscriptionPayWizard(models.TransientModel):
    _name = 'havanoposdesk.subscription.pay.wizard'
    _description = 'Pay Subscription Wizard'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', required=True)
    amount = fields.Float(string='Amount to Pay', required=True)
    payment_method = fields.Selection([
        ('paynow', 'Paynow Card (Redirection)'),
        ('ecocash', 'EcoCash Mobile')
    ], string='Payment Method', default='paynow', required=True)
    phone = fields.Char(string='EcoCash Phone Number', help="Enter number starting with 077... or 078...")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            tenant = self.env['havanoposdesk.tenant'].browse(active_id)
            plan = tenant.pending_subscription_plan_id or tenant.subscription_plan_id
            amount = tenant.pending_subscription_total_amount if tenant.pending_subscription_plan_id else (tenant.subscription_total_amount or (plan.price if plan else 0.0))
            res.update({
                'tenant_id': tenant.id,
                'subscription_plan_id': plan.id if plan else False,
                'amount': amount,
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


class HavanoposdeskTenantTopupWizard(models.TransientModel):
    _name = 'havanoposdesk.tenant.topup.wizard'
    _description = 'Top Up Account Balance Wizard'

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True)
    amount = fields.Float(string='Top Up Amount ($)', default=10.0, required=True)
    payment_method = fields.Selection([
        ('paynow', 'Paynow Card / Online'),
        ('ecocash', 'EcoCash Mobile'),
        ('manual', 'Manual / Admin Credit')
    ], string='Payment Method', default='paynow', required=True)
    phone = fields.Char(string='EcoCash Phone Number', help="Enter number starting with 077... or 078...")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['tenant_id'] = active_id
        return res

    def action_topup(self):
        self.ensure_one()
        if self.amount <= 0:
            raise ValidationError('Top-up amount must be greater than zero.')

        is_super = self.env.user.havano_role == 'super_admin' or self.env.user.has_group('base.group_system') or self.env.su

        # Manual / Admin Credit processing
        if self.payment_method == 'manual':
            if is_super:
                new_balance = self.tenant_id.account_balance + self.amount
                self.tenant_id.with_context(bypass_subscription_check=True).write({'account_balance': new_balance})
                
                import time
                ref = f"TOP-{self.tenant_id.id}-MANUAL-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
                self.env['havanoposdesk.subscription.payment'].create({
                    'tenant_id': self.tenant_id.id,
                    'amount': self.amount,
                    'payment_method': 'manual',
                    'payment_type': 'topup',
                    'transaction_reference': ref,
                    'state': 'done',
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Account Balance Credited',
                        'message': f'Successfully added ${self.amount:.2f} to account balance.',
                        'type': 'success',
                        'sticky': False,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }
            else:
                import time
                ref = f"TOP-{self.tenant_id.id}-REQ-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
                self.env['havanoposdesk.subscription.payment'].create({
                    'tenant_id': self.tenant_id.id,
                    'amount': self.amount,
                    'payment_method': 'manual',
                    'payment_type': 'topup',
                    'transaction_reference': ref,
                    'state': 'pending',
                })
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Top-Up Request Submitted',
                        'message': f'Your top-up request for ${self.amount:.2f} has been submitted. A Super Admin will review and approve it.',
                        'type': 'info',
                        'sticky': True,
                        'next': {'type': 'ir.actions.act_window_close'},
                    }
                }

        provider = self.env['payment.provider'].sudo().search([('code', '=', 'havano_payments')], limit=1)
        if not provider:
            raise ValidationError('Havano Payments provider is not configured. Please configure it in SaaS Config.')

        import time
        reference = f"TOP-{self.tenant_id.id}-{fields.Datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"

        subscription_payment = self.env['havanoposdesk.subscription.payment'].create({
            'tenant_id': self.tenant_id.id,
            'amount': self.amount,
            'payment_method': self.payment_method,
            'payment_type': 'topup',
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
                additional_info=f"Account Top-Up for {self.tenant_id.name}"
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
                    'message': mobile_res.get('instructions') or 'A prompt was sent to your phone. Please enter your PIN to complete top-up.',
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
                additional_info=f"Account Top-Up for {self.tenant_id.name}"
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
