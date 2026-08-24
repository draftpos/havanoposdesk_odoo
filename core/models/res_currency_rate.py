from odoo import models, fields, api, _
from odoo.exceptions import UserError

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    name = fields.Datetime(string='Date', required=True, index=True, default=fields.Datetime.now)
    currency_id = fields.Many2one('res.currency', readonly=False)
    tenant_id = fields.Many2one(related='currency_id.tenant_id', store=True, readonly=True, index=True)

    _unique_name_per_day = models.Constraint('CHECK (TRUE)')

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
        # Only allow writing during creation (when no ID yet) or system operations
        # For existing records, block changes to rate fields
        rate_fields = {'company_rate', 'inverse_company_rate', 'rate', 'name', 'currency_id'}
        if rate_fields & set(vals.keys()):
            for rate in self:
                if rate.id and isinstance(rate.id, int):
                    raise UserError(_("Exchange rates cannot be modified. Please add a new rate entry instead."))
        return super().write(vals)

    def unlink(self):
        raise UserError(_("Exchange rates cannot be deleted. They are kept for historical audit purposes."))

