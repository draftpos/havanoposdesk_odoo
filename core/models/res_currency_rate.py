from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    currency_id = fields.Many2one('res.currency', readonly=False)
    tenant_id = fields.Many2one(related='currency_id.tenant_id', store=True, readonly=True, index=True)

    def _check_access(self, operation: str):
        if operation == 'read':
            return None
        return super()._check_access(operation)

    def check_access(self, operation: str) -> None:
        if operation == 'read':
            return None
        return super().check_access(operation)

    def check_access_rights(self, operation, raise_exception=True):
        if operation == 'read':
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

    def write(self, vals):
        for rate in self:
            if rate._is_used_in_transactions():
                raise UserError(_("This exchange rate cannot be modified because it has been used in sales or payments transactions."))
        return super().write(vals)

    def unlink(self):
        for rate in self:
            if rate._is_used_in_transactions():
                raise UserError(_("This exchange rate cannot be deleted because it has been used in sales or payments transactions."))
        return super().unlink()

    def _is_used_in_transactions(self):
        self.ensure_one()
        # Check sales
        Sale = self.env['havanoposdesk.sale']
        sales = Sale.search([
            ('currency_id', '=', self.currency_id.id),
            ('posting_date', '=', self.name),
            ('state', 'in', ['confirmed', 'done'])
        ], limit=1)
        if sales:
            return True

        # Check payments
        Payment = self.env['havanoposdesk.payment']
        payments = Payment.search([
            ('currency_id', '=', self.currency_id.id),
            ('date', '=', self.name),
            ('state', '=', 'posted')
        ], limit=1)
        if payments:
            return True

        # Check payment lines
        PaymentLine = self.env['havanoposdesk.payment.line']
        payment_lines = PaymentLine.search([
            ('currency_id', '=', self.currency_id.id),
            ('payment_id.date', '=', self.name),
            ('payment_id.state', '=', 'posted')
        ], limit=1)
        if payment_lines:
            return True

        return False

