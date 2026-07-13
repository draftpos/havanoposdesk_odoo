from odoo import models, fields, api

class HavanoposdeskProduct(models.Model):
    _name = 'havanoposdesk.product'
    _description = 'Product'
    _rec_names_search = ['name', 'item_code']

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'The product name must be unique per tenant!'),
        ('item_code_tenant_uniq', 'unique (item_code, tenant_id)', 'The Product Code must be unique per tenant!'),
        ('barcode_tenant_uniq', 'unique (barcode, tenant_id)', 'The Product Barcode must be unique per tenant!')
    ]

    name = fields.Char(string='Product Name', required=True)
    item_code = fields.Char(string='Product Code', required=True, copy=False, readonly=True, default=lambda self: 'New')
    barcode = fields.Char(string='Barcode', copy=False)
    is_barcode_enabled = fields.Boolean(related='tenant_id.enable_barcode', string="Barcode Enabled")

    @api.depends('name', 'item_code', 'tenant_id')
    def _compute_display_name(self):
        is_super_admin = self.env.user.has_group('base.group_system')
        for record in self:
            base_name = f"[{record.item_code}] {record.name}" if record.item_code and record.item_code != 'New' else record.name
            if is_super_admin and record.tenant_id:
                record.display_name = f"{base_name} ({record.tenant_id.name})"
            else:
                record.display_name = base_name

    @api.model
    def _name_search(self, name='', args=None, operator='ilike', limit=100, name_get_uid=None):
        args = list(args or [])
        if name:
            args += ['|', ('name', operator, name), ('item_code', operator, name)]
        return self._search(args, limit=limit, access_rights_uid=name_get_uid)
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
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
            
            if 'name' in vals and vals['name'] and tenant and tenant.product_name_format:
                if tenant.product_name_format == 'uppercase':
                    vals['name'] = vals['name'].upper()
                elif tenant.product_name_format == 'lowercase':
                    vals['name'] = vals['name'].lower()
                elif tenant.product_name_format == 'title':
                    vals['name'] = vals['name'].title()
                    
            if vals.get('item_code', 'New') == 'New':
                if tenant:
                    vals['item_code'] = tenant._get_next_sequence('prod')
                else:
                    vals['item_code'] = self.env['ir.sequence'].next_by_code('havanoposdesk.product') or 'New'
        products = super().create(vals_list)
        
        for product in products:
            if product.opening_stock > 0:
                adj = self.env['havanoposdesk.stock.adjustment'].with_context(from_product_creation=True).create({
                    'store_id': product.store_ids[0].id if product.store_ids else False,
                    'fetch_all_data': False,
                    'line_ids': [(0, 0, {
                        'product_id': product.id,
                        'on_hand': product.opening_stock,
                        'counted': product.opening_stock,
                    })]
                })
                adj.action_post()
                
            if product.allow_advanced_pricing and product.store_ids and product.uom_id:
                default_pricelist = self.env['havanoposdesk.pricelist'].search([('tenant_id', '=', product.tenant_id.id), ('name', 'ilike', 'Retail')], limit=1)
                if not default_pricelist:
                    default_pricelist = self.env['havanoposdesk.pricelist'].search([('tenant_id', '=', product.tenant_id.id)], limit=1)
                if not default_pricelist:
                    default_pricelist = self.env['havanoposdesk.pricelist'].create({'name': 'Retail', 'tenant_id': product.tenant_id.id})
                
                for store in product.store_ids:
                    self.env['havanoposdesk.product.uom.price'].create({
                        'product_id': product.id,
                        'store_id': store.id,
                        'pricelist_id': default_pricelist.id,
                        'uom_id': product.uom_id.id,
                        'qty_to_be_sold': 1.0,
                        'price': product.selling_price,
                        'tenant_id': product.tenant_id.id
                    })
        return products

    def write(self, vals):
        if 'name' in vals and vals['name']:
            for product in self:
                fmt = product.tenant_id.product_name_format
                if fmt == 'uppercase':
                    vals['name'] = vals['name'].upper()
                elif fmt == 'lowercase':
                    vals['name'] = vals['name'].lower()
                elif fmt == 'title':
                    vals['name'] = vals['name'].title()
                break # All products in self usually belong to same tenant, or we can just apply first one
        return super().write(vals)

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
    currency_id = fields.Many2one(related='tenant_id.currency_id', string='Currency', store=False)
    advanced_price_ids = fields.One2many('havanoposdesk.product.uom.price', 'product_id', string='Advanced Prices')
    allow_advanced_pricing = fields.Boolean(related='tenant_id.allow_advanced_pricing', readonly=True)

    def _get_default_stores(self):
        tenant_id = self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        # Look for the store explicitly marked as default for this tenant
        default_store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id), ('is_default', '=', True)], limit=1)
        if default_store:
            return [(6, 0, [default_store.id])]
        # Fallback to user's personal default or the first available store
        fallback = self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1).id
        if fallback:
            return [(6, 0, [fallback])]
        return []

    store_ids = fields.Many2many('havanoposdesk.store', 'product_store_rel', 'product_id', 'store_id', string='Stores', required=True, default=_get_default_stores)
    all_stores = fields.Boolean(string='All Stores', default=True)
    has_multiple_stores = fields.Boolean(compute='_compute_has_multiple_stores')

    @api.depends('tenant_id')
    def _compute_has_multiple_stores(self):
        for record in self:
            store_count = self.env['havanoposdesk.store'].search_count([('tenant_id', '=', record.tenant_id.id)])
            record.has_multiple_stores = store_count > 1

    @api.onchange('all_stores')
    def _onchange_all_stores(self):
        if self.all_stores:
            all_store_records = self.env['havanoposdesk.store'].search([('tenant_id', '=', self.tenant_id.id)])
            self.store_ids = [(6, 0, all_store_records.ids)]

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
