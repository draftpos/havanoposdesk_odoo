from odoo import models, fields

class ResCurrencyRate(models.Model):
    _inherit = 'res.currency.rate'

    currency_id = fields.Many2one('res.currency', readonly=False)
