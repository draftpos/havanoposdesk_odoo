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
    buying_price = fields.Float(string='Cost Price', compute='_compute_prices', store=True, readonly=False)
    selling_price = fields.Float(string='Sell Price', compute='_compute_prices', store=True, readonly=False)
    subtotal_cost = fields.Float(string='Total Cost', compute='_compute_subtotals', store=True)
    subtotal_selling = fields.Float(string='Total Sell', compute='_compute_subtotals', store=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )

    @api.depends('product_id')
    def _compute_prices(self):
        for item in self:
            if item.product_id:
                if not item.buying_price:
                    item.buying_price = item.product_id.buying_price or 0.0
                if not item.selling_price:
                    item.selling_price = item.product_id.selling_price or 0.0

    @api.depends('qty', 'buying_price', 'selling_price')
    def _compute_subtotals(self):
        for item in self:
            item.subtotal_cost = (item.qty or 0.0) * (item.buying_price or 0.0)
            item.subtotal_selling = (item.qty or 0.0) * (item.selling_price or 0.0)

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.buying_price = self.product_id.buying_price or 0.0
            self.selling_price = self.product_id.selling_price or 0.0
