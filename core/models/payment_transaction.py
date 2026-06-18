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
                tx.subscription_payment_id.write({
                    'state': 'done', 
                    'transaction_reference': tx.reference
                })
                tx.subscription_payment_id.tenant_id.action_pay_and_activate()
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
