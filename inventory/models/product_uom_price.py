from odoo import models, fields, api

class HavanoposdeskProductUomPrice(models.Model):
    _name = 'havanoposdesk.product.uom.price'
    _description = 'Product UOM Price'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True, ondelete='cascade')
    pricelist_id = fields.Many2one('havanoposdesk.pricelist', string='Pricelist', required=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UoM Name', required=True)
    qty_to_be_sold = fields.Float(string='Qty to be Sold', default=1.0, required=True, help="Conversion multiplier (e.g. 1 Box = 24 items, set this to 24)")
    price = fields.Float(string='Price', required=True, default=0.0)

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        required=True,
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
