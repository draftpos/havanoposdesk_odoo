from odoo import models, fields, api

class HavanoposdeskProduct(models.Model):
    _name = 'havanoposdesk.product'
    _description = 'Product'
    _rec_names_search = ['name', 'item_code']

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'The product name must be unique per tenant!'),
        ('item_code_tenant_uniq', 'unique (item_code, tenant_id)', 'The Product Code must be unique per tenant!')
    ]

    name = fields.Char(string='Product Name', required=True)
    item_code = fields.Char(string='Product Code', required=True, copy=False, readonly=True, default=lambda self: 'New')

    @api.depends('name', 'item_code')
    def _compute_display_name(self):
        for record in self:
            if record.item_code and record.item_code != 'New':
                record.display_name = f"[{record.item_code}] {record.name}"
            else:
                record.display_name = record.name
    buying_price = fields.Float(string='Cost price', default=0.0)
    selling_price = fields.Float(string='Sell price')
    markup = fields.Float(string='Markup', compute='_compute_markup')
    cost_price = fields.Float(string='Cost Price')
    track_qty = fields.Boolean(string='Track Qty', default=True)
    opening_stock = fields.Float(string='Opening Stock', default=0.0)

    sale_tax_ids = fields.Many2many('havanoposdesk.tax', 'product_sale_tax_rel', 'product_id', 'tax_id', string='Sales Taxes', domain=[('tax_type', '=', 'Sales'), ('active', '=', True)])
    purchase_tax_ids = fields.Many2many('havanoposdesk.tax', 'product_purchase_tax_rel', 'product_id', 'tax_id', string='Purchase Taxes', domain=[('tax_type', '=', 'Purchases'), ('active', '=', True)])
    has_active_taxes = fields.Boolean(compute='_compute_has_active_taxes')
    buy_price_with_tax = fields.Float(string='Buy Price With Tax', compute='_compute_prices_with_tax')
    sell_price_with_tax = fields.Float(string='Sell Price With Tax', compute='_compute_prices_with_tax')

    @api.depends('buying_price', 'selling_price', 'purchase_tax_ids', 'sale_tax_ids')
    def _compute_prices_with_tax(self):
        for record in self:
            # Buy Price
            buy_price = record.buying_price
            purchase_taxes = record.purchase_tax_ids
            inclusive_ptaxes = purchase_taxes.filtered(lambda t: t.is_inclusive)
            exclusive_ptaxes = purchase_taxes.filtered(lambda t: not t.is_inclusive)
            
            p_rate_incl = sum(inclusive_ptaxes.mapped('rate')) / 100.0
            p_rate_excl = sum(exclusive_ptaxes.mapped('rate')) / 100.0
            
            if p_rate_incl > 0:
                p_untaxed = buy_price / (1.0 + p_rate_incl)
                record.buy_price_with_tax = buy_price + (p_untaxed * p_rate_excl)
            else:
                record.buy_price_with_tax = buy_price * (1.0 + p_rate_excl)
            
            # Sell Price
            sell_price = record.selling_price
            sale_taxes = record.sale_tax_ids
            inclusive_staxes = sale_taxes.filtered(lambda t: t.is_inclusive)
            exclusive_staxes = sale_taxes.filtered(lambda t: not t.is_inclusive)
            
            s_rate_incl = sum(inclusive_staxes.mapped('rate')) / 100.0
            s_rate_excl = sum(exclusive_staxes.mapped('rate')) / 100.0
            
            if s_rate_incl > 0:
                s_untaxed = sell_price / (1.0 + s_rate_incl)
                record.sell_price_with_tax = sell_price + (s_untaxed * s_rate_excl)
            else:
                record.sell_price_with_tax = sell_price * (1.0 + s_rate_excl)

    @api.depends()
    def _compute_has_active_taxes(self):
        has_taxes = bool(self.env['havanoposdesk.tax'].search([('active', '=', True)], limit=1))
        for record in self:
            record.has_active_taxes = has_taxes

    @api.onchange('sale_tax_ids')
    def _onchange_sale_tax_ids(self):
        tenant_id = self.env.user.tenant_id.id
        purchase_tax_ids = []
        for sale_tax in self.sale_tax_ids:
            # 1. Search by name first (exact name match)
            matching_purchase_tax = self.env['havanoposdesk.tax'].search([
                ('tax_type', '=', 'Purchases'),
                ('active', '=', True),
                ('name', '=', sale_tax.name),
                ('tenant_id', '=', tenant_id)
            ], limit=1)
            
            # 2. Fallback to rate & inclusive configuration
            if not matching_purchase_tax:
                matching_purchase_tax = self.env['havanoposdesk.tax'].search([
                    ('tax_type', '=', 'Purchases'),
                    ('active', '=', True),
                    ('rate', '=', sale_tax.rate),
                    ('is_inclusive', '=', sale_tax.is_inclusive),
                    ('tenant_id', '=', tenant_id)
                ], limit=1)
                
            if matching_purchase_tax:
                purchase_tax_ids.append(matching_purchase_tax.id)
        self.purchase_tax_ids = [(6, 0, purchase_tax_ids)]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('item_code', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['item_code'] = tenant._get_next_sequence('prod')
                else:
                    vals['item_code'] = self.env['ir.sequence'].next_by_code('havanoposdesk.product') or 'New'
        products = super().create(vals_list)
        
        for product in products:
            if product.opening_stock > 0:
                adj = self.env['havanoposdesk.stock.adjustment'].with_context(from_product_creation=True).create({
                    'store_id': product.store_id.id if product.store_id else False,
                    'fetch_all_data': False,
                    'line_ids': [(0, 0, {
                        'product_id': product.id,
                        'on_hand': product.opening_stock,
                        'counted': product.opening_stock,
                    })]
                })
                adj.action_post()
        return products

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
    advanced_price_ids = fields.One2many('havanoposdesk.product.uom.price', 'product_id', string='Advanced Prices')
    allow_advanced_pricing = fields.Boolean(related='tenant_id.allow_advanced_pricing', readonly=True)

    def _get_default_store(self):
        tenant_id = self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        # Look for the store explicitly marked as default for this tenant
        default_store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id), ('is_default', '=', True)], limit=1)
        if default_store:
            return default_store.id
        # Fallback to user's personal default or the first available store
        return self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1).id

    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True, default=_get_default_store)

    @api.depends('buying_price', 'selling_price')
    def _compute_markup(self):
        for record in self:
            if record.buying_price > 0:
                record.markup = ((record.selling_price - record.buying_price) / record.buying_price) * 100
            else:
                record.markup = 0.0

    def action_save(self):
        return True

class HavanoposdeskProductCosting(models.Model):
    _name = 'havanoposdesk.product.costing'
    _description = 'Product Costing Table'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True, ondelete='cascade')
    purchase_line_id = fields.Many2one('havanoposdesk.purchase.line', string='Purchase Line', ondelete='cascade')
    date = fields.Date(string='Date', default=fields.Date.context_today)
    qty = fields.Float(string='Quantity')
    price = fields.Float(string='Price/Rate')
    cost_type = fields.Selection([('last', 'Last Purchase'), ('average', 'Average')], string='Cost Type', default='last')
