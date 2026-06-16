from odoo import models, fields, api

class HavanoposdeskProduct(models.Model):
    _name = 'havanoposdesk.product'
    _description = 'Product'

    name = fields.Char(string='Name', required=True)
    item_code = fields.Char(string='Item Code')
    buying_price = fields.Float(string='Buying Price', default=0.0)
    selling_price = fields.Float(string='Selling Price')
    markup = fields.Float(string='Markup', compute='_compute_markup')
    cost_price = fields.Float(string='Cost Price')
    track_qty = fields.Boolean(string='Track Qty', default=True)
    opening_stock = fields.Float(string='Opening Stock', default=0.0)
    color_hex = fields.Char(string='Color Hex')
    image_1920 = fields.Image(string='Image', max_width=1920, max_height=1920)
    
    # Advanced Pricing
    discount_percentage = fields.Float(string='Discount Percentage')
    tax_percentage = fields.Float(string='Tax Percentage')
    
    # Other
    internal_notes = fields.Text(string='Internal Notes')
    is_active = fields.Boolean(string='Active', default=True)
    
    category_id = fields.Many2one('havanoposdesk.category', string='Category')
    uom_id = fields.Many2one('havanoposdesk.uom', string='Unit of Measure')
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env['havanoposdesk.tenant'].search([], limit=1).id)

    @api.depends('buying_price', 'selling_price')
    def _compute_markup(self):
        for record in self:
            if record.buying_price > 0:
                record.markup = ((record.selling_price - record.buying_price) / record.buying_price) * 100
            else:
                record.markup = 0.0
