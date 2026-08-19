from odoo import models, fields

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    currency_id = fields.Many2one('res.currency', readonly=False)
    tenant_id = fields.Many2one(related='currency_id.tenant_id', store=True, readonly=True, index=True)
