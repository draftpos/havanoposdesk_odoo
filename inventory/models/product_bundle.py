from odoo import models, fields, api

class HavanoposdeskProductBundleItem(models.Model):
    _name = 'havanoposdesk.product.bundle.item'
    _description = 'Product Bundle Component Item'

    parent_product_id = fields.Many2one(
        'havanoposdesk.product', 
        string='Parent Product (Bundle)', 
        required=True, 
        ondelete='cascade', 
        domain="[('is_bundle', '=', True)]"
    )
    product_id = fields.Many2one(
        'havanoposdesk.product', 
        string='Component Product', 
        required=True, 
        ondelete='cascade'
    )
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
