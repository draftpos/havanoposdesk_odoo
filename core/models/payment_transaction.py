from odoo import models, fields, _

class PaymentTransaction(models.Model):
    _inherit = 'payment.transaction'

    subscription_payment_id = fields.Many2one(
        'havanoposdesk.subscription.payment', 
        string="Subscription Payment"
    )

    def _set_done(self, **kwargs):
        res = super()._set_done(**kwargs)
        for tx in self:
            if tx.subscription_payment_id:
                sub_pay = tx.subscription_payment_id
                sub_pay.write({
                    'state': 'done', 
                    'transaction_reference': tx.reference
                })
                tenant = sub_pay.tenant_id
                if sub_pay.payment_type == 'topup':
                    new_balance = tenant.account_balance + tx.amount
                    tenant.with_context(bypass_subscription_check=True).write({'account_balance': new_balance})
                else:
                    tenant.action_pay_and_activate()
        return res

    def _set_pending(self, **kwargs):
        res = super()._set_pending(**kwargs)
        for tx in self:
            if tx.subscription_payment_id:
                tx.subscription_payment_id.write({'state': 'pending'})
        return res

    def _set_canceled(self, **kwargs):
        res = super()._set_canceled(**kwargs)
        for tx in self:
            if tx.subscription_payment_id:
                tx.subscription_payment_id.write({'state': 'failed'})
        return res

    def _set_error(self, *args, **kwargs):
        res = super()._set_error(*args, **kwargs)
        for tx in self:
            if tx.subscription_payment_id:
                tx.subscription_payment_id.write({'state': 'failed'})
        return res
