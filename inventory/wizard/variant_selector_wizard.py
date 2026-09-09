from odoo import models, fields, api

class VariantSelectorWizard(models.TransientModel):
    _name = 'havanoposdesk.variant.selector'
    _description = 'Select Product Variant'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True)
    variant_id = fields.Many2one('havanoposdesk.product.variant', string='Variant', required=True, domain="[('product_id', '=', product_id)]")
    
    def action_confirm(self):
        # We need a way to pass the selection back. 
        # Typically handled by frontend or by passing context
        pass