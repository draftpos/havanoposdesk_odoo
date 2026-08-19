from odoo import models, fields

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

