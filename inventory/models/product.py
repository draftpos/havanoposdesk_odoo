from odoo import models, fields, api

class HavanoposdeskProduct(models.Model):
    _name = 'havanoposdesk.product'
    _description = 'Product'

    name = fields.Char(string='Product Name', required=True)
    item_code = fields.Char(string='Item Code', required=True, copy=False, readonly=True, default=lambda self: 'New')
    buying_price = fields.Float(string='Buy price', default=0.0)
    selling_price = fields.Float(string='Sell price')
    markup = fields.Float(string='Markup', compute='_compute_markup')
    cost_price = fields.Float(string='Cost Price')
    track_qty = fields.Boolean(string='Track Qty', default=True)
    opening_stock = fields.Float(string='Opening Stock', default=0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('item_code', 'New') == 'New':
                vals['item_code'] = self.env['ir.sequence'].next_by_code('havanoposdesk.product') or 'New'
        return super().create(vals_list)

    color_hex = fields.Char(string='Color Hex')
    color = fields.Selection([
        ('red', 'Red'),
        ('blue', 'Blue'),
        ('green', 'Green'),
        ('yellow', 'Yellow'),
        ('orange', 'Orange'),
        ('purple', 'Purple'),
        ('brown', 'Brown'),
        ('black', 'Black'),
        ('white', 'White'),
    ], string='Color')
    image_1920 = fields.Image(string='Image', max_width=1920, max_height=1920)
    
    # Advanced Pricing
    discount_percentage = fields.Float(string='Discount Percentage')
    tax_percentage = fields.Float(string='Tax Percentage')
    
    # Other
    internal_notes = fields.Text(string='Internal Notes')
    is_active = fields.Boolean(string='Active', default=True)
    
    category_id = fields.Many2one('havanoposdesk.category', string='Category', default=lambda self: (self.env['havanoposdesk.category'].search([('name', '=', 'Basics')], limit=1) or self.env['havanoposdesk.category'].create({'name': 'Basics'})).id)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', default=lambda self: (self.env['havanoposdesk.uom'].search([('name', '=', 'Each')], limit=1) or self.env['havanoposdesk.uom'].create({'name': 'Each'})).id)
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id)
    def _default_store_id(self):
        tenant_id = self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        # Look for the store explicitly marked as default for this tenant
        default_store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id), ('is_default', '=', True)], limit=1)
        if default_store:
            return default_store.id
        # Fallback to user's personal default or the first available store
        return self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1).id

    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True, default=_default_store_id)

    @api.depends('buying_price', 'selling_price')
    def _compute_markup(self):
        for record in self:
            if record.buying_price > 0:
                record.markup = ((record.selling_price - record.buying_price) / record.buying_price) * 100
            else:
                record.markup = 0.0

    def action_save(self):
        return True
