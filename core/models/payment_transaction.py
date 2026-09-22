import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)

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
                    'transaction_reference': tx.provider_reference or tx.reference
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

    @api.model
    def cron_poll_pending_paynow_transactions(self):
        """ Automatically polls pending Paynow/EcoCash transactions to reconcile completed payments """
        import datetime
        from odoo.addons.havano_payments.models.paynow_client import PaynowClient

        time_limit = fields.Datetime.now() - datetime.timedelta(hours=2)
        pending_txs = self.search([
            ('provider_code', '=', 'havano_payments'),
            ('state', '=', 'pending'),
            ('paynow_poll_url', '!=', False),
            ('create_date', '>=', time_limit),
        ])
        for tx in pending_txs:
            try:
                if not tx.provider_id or not tx.provider_id.paynow_integration_id or not tx.provider_id.paynow_integration_key:
                    continue
                client = PaynowClient(tx.provider_id.paynow_integration_id, tx.provider_id.paynow_integration_key)
                status_res = client.poll_transaction_status(tx.paynow_poll_url)
                status = (status_res.get('status') or '').lower()
                if status in ('paid', 'awaiting delivery', 'cancelled', 'canceled', 'failed'):
                    tx._process('havano_payments', status_res)
                    self.env.cr.commit()
            except Exception as e:
                _logger.warning("Error auto-polling Paynow tx %s: %s", tx.reference, e)

