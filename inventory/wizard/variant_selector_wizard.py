from odoo import models, fields, api

class VariantSelectorWizard(models.TransientModel):
    _name = 'havanoposdesk.variant.selector'
    _description = 'Select Product Variant'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True)
    variant_id = fields.Many2one('havanoposdesk.product.variant', string='Variant', required=True, domain="[('product_id', '=', product_id)]")
    
    def action_confirm(self):
        active_model = self.env.context.get('active_model')
        active_id = self.env.context.get('active_id')
        if active_model and active_id:
            record = self.env[active_model].browse(active_id)
            if hasattr(record, 'variant_id'):
                record.variant_id = self.variant_id.id
                # Force rate/cost update if onchange methods exist
                if hasattr(record, '_onchange_variant_id'):
                    record._onchange_variant_id()
                elif hasattr(record, '_onchange_product_id'):
                    record._onchange_product_id()
        return {'type': 'ir.actions.act_window_close'}