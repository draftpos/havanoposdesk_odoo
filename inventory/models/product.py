from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HavanoposdeskProduct(models.Model):
    _name = 'havanoposdesk.product'
    _inherit = ['havanoposdesk.audit.mixin']
    _description = 'Product'
    _rec_names_search = ['name', 'item_code']

    def _auto_init(self):
        res = super()._auto_init()
        cr = self.env.cr
        try:
            with cr.savepoint():
                cr.execute("ALTER TABLE havanoposdesk_product ADD COLUMN IF NOT EXISTS sellbyprice BOOLEAN DEFAULT FALSE;")
        except Exception:
            pass
        return res

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'The product name must be unique per tenant!'),
        ('item_code_tenant_uniq', 'unique (item_code, tenant_id)', 'The Product Code must be unique per tenant!'),
        ('barcode_tenant_uniq', 'unique (barcode, tenant_id)', 'The Product Barcode must be unique per tenant!')
    ]

    name = fields.Char(string='Product Name', required=True)
    item_code = fields.Char(string='Product Code', required=False, copy=False, default=lambda self: 'New')
    allow_edit_item_code = fields.Boolean(related='tenant_id.allow_edit_item_code', string="Allow Edit Item Code")
    barcode = fields.Char(string='Barcode', copy=False)
    is_barcode_enabled = fields.Boolean(related='tenant_id.enable_barcode', string="Barcode Enabled")
    sellbyprice = fields.Boolean(
        string='Sell by Price',
        default=False,
        help='If enabled, allows selling this item by entering the total price first, which automatically calculates the quantity.'
    )

    @api.constrains('name', 'tenant_id')
    def _check_unique_name(self):
        for record in self:
            if record.name and record.tenant_id:
                domain = [
                    ('id', '!=', record.id),
                    ('tenant_id', '=', record.tenant_id.id),
                    ('name', '=ilike', record.name.strip())
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(f"A Product with the name '{record.name}' already exists in your workspace. Please choose a different name.")

    @api.constrains('item_code', 'tenant_id')
    def _check_unique_item_code(self):
        for record in self:
            if record.item_code and record.item_code != 'New' and record.tenant_id:
                domain = [
                    ('id', '!=', record.id),
                    ('tenant_id', '=', record.tenant_id.id),
                    ('item_code', '=', record.item_code.strip())
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(
                        f"A Product with the code '{record.item_code}' already exists in your workspace. Please choose a different code."
                    )

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
    def default_get(self, fields_list):
        res = super(HavanoposdeskProduct, self).default_get(fields_list)
        if 'item_code' in fields_list and res.get('item_code') == 'New':
            tenant = self.env.user.tenant_id
            if tenant:
                res['item_code'] = tenant._get_next_sequence('prod')
            else:
                res['item_code'] = self.env['ir.sequence'].next_by_code('havanoposdesk.product') or 'New'
        return res
    buying_price = fields.Float(string='Cost price', default=0.0, compute='_compute_bundle_prices', store=True, readonly=False)
    selling_price = fields.Float(string='Sell price', compute='_compute_bundle_prices', inverse='_inverse_selling_price', store=True, readonly=False)
    uom_price_ids = fields.One2many('havanoposdesk.product.uom.price', 'product_id', string='UOM Prices')
    markup = fields.Float(string='Markup', compute='_compute_markup')
    cost_price = fields.Float(string='Cost Price')
    track_qty = fields.Boolean(string='Track Qty', default=True)
    opening_stock = fields.Float(string='Opening Stock', default=0.0)
    on_hand_qty = fields.Float(string='On Hand', compute='_compute_on_hand_qty')

    @api.depends('is_bundle')
    def _compute_on_hand_qty(self):
        for record in self:
            if record.is_bundle:
                record.on_hand_qty = 0.0
            else:
                valuations = self.env['havanoposdesk.stock.valuation'].search([('product_id', '=', record.id)])
                record.on_hand_qty = sum(valuations.mapped('on_hand_qty'))

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

    @api.depends('tenant_id')
    def _compute_has_active_taxes(self):
        for record in self:
            tenant_id = record.tenant_id.id if record.tenant_id else self.env.user.tenant_id.id
            record.has_active_taxes = bool(self.env['havanoposdesk.tax'].search([('active', '=', True), ('tenant_id', '=', tenant_id)], limit=1))

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
            
            # Map store_id to store_ids if present and pop it to prevent invalid field exception
            if 'store_id' in vals:
                store_id = vals.pop('store_id')
                if store_id and 'store_ids' not in vals:
                    vals['store_ids'] = [(6, 0, [store_id])]

            if 'name' in vals and vals['name'] and tenant and tenant.product_name_format:
                if tenant.product_name_format == 'uppercase':
                    vals['name'] = vals['name'].upper()
                elif tenant.product_name_format == 'lowercase':
                    vals['name'] = vals['name'].lower()
                elif tenant.product_name_format == 'title':
                    vals['name'] = vals['name'].title()
                    
            if not vals.get('item_code') or vals.get('item_code') == 'New':
                if tenant:
                    vals['item_code'] = tenant._get_next_sequence('prod')
                else:
                    vals['item_code'] = self.env['ir.sequence'].next_by_code('havanoposdesk.product') or 'New'

            # Auto-map purchase_tax_ids from sale_tax_ids if not provided
            if 'sale_tax_ids' in vals and 'purchase_tax_ids' not in vals:
                raw_ids = []
                if isinstance(vals['sale_tax_ids'], list):
                    for item in vals['sale_tax_ids']:
                        if isinstance(item, (list, tuple)) and len(item) == 3 and item[0] == 6:
                            raw_ids.extend(item[2])
                        elif isinstance(item, int):
                            raw_ids.append(item)
                if raw_ids:
                    sale_taxes = self.env['havanoposdesk.tax'].sudo().browse(raw_ids)
                    purchase_tax_ids = []
                    for sale_tax in sale_taxes:
                        matching_ptax = self.env['havanoposdesk.tax'].sudo().search([
                            ('tax_type', '=', 'Purchases'),
                            ('active', '=', True),
                            ('name', '=', sale_tax.name),
                            ('tenant_id', '=', tenant_id)
                        ], limit=1)
                        if not matching_ptax:
                            matching_ptax = self.env['havanoposdesk.tax'].sudo().search([
                                ('tax_type', '=', 'Purchases'),
                                ('active', '=', True),
                                ('rate', '=', sale_tax.rate),
                                ('is_inclusive', '=', sale_tax.is_inclusive),
                                ('tenant_id', '=', tenant_id)
                            ], limit=1)
                        if matching_ptax:
                            purchase_tax_ids.append(matching_ptax.id)
                    if purchase_tax_ids:
                        vals['purchase_tax_ids'] = [(6, 0, purchase_tax_ids)]

            # Set store_ids to all stores if all_stores is True (either by default or explicitly)
            if (vals.get('all_stores', True) and 'store_ids' not in vals) or vals.get('all_stores') is True:
                if tenant_id:
                    all_store_records = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)])
                    if all_store_records:
                        vals['store_ids'] = [(6, 0, all_store_records.ids)]
        products = super().create(vals_list)
        
        for product in products:
            if product.opening_stock > 0:
                adj = self.env['havanoposdesk.stock.adjustment'].with_context(from_product_creation=True).create({
                    'store_id': product.store_ids[0].id if product.store_ids else False,
                    'fetch_all_data': False,
                    'tenant_id': product.tenant_id.id,
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
                    existing = self.env['havanoposdesk.product.uom.price'].search([
                        ('product_id', '=', product.id),
                        ('store_id', '=', store.id),
                        ('pricelist_id', '=', default_pricelist.id),
                        ('uom_id', '=', product.uom_id.id)
                    ], limit=1)
                    if not existing:
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
        # Map store_id to store_ids if present and pop it to prevent invalid field exception
        if 'store_id' in vals:
            store_id = vals.pop('store_id')
            if store_id:
                vals['store_ids'] = [(6, 0, [store_id])]

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

        res = super().write(vals)

        if vals.get('all_stores'):
            for product in self:
                all_store_records = self.env['havanoposdesk.store'].search([('tenant_id', '=', product.tenant_id.id)])
                super(HavanoposdeskProduct, product).write({
                    'store_ids': [(6, 0, all_store_records.ids)]
                })
        return res

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
    not_for_sale = fields.Boolean(string='Not For Sale', default=False)
    
    # Advanced Pricing
    discount_percentage = fields.Float(string='Discount Percentage')
    tax_percentage = fields.Float(string='Tax Percentage')
    
    # Other
    internal_notes = fields.Text(string='Internal Notes')
    is_active = fields.Boolean(string='Active', default=True)
    kitchen_settings_enabled = fields.Boolean(
        related='tenant_id.enable_kitchen_settings',
        string='Kitchen Settings Enabled'
    )
    kitchen_order_1 = fields.Boolean(string='Order 1', default=False)
    kitchen_order_2 = fields.Boolean(string='Order 2', default=False)
    kitchen_order_3 = fields.Boolean(string='Order 3', default=False)
    kitchen_order_4 = fields.Boolean(string='Order 4', default=False)
    kitchen_order_5 = fields.Boolean(string='Order 5', default=False)
    kitchen_order_6 = fields.Boolean(string='Order 6', default=False)
    kitchen_order_7 = fields.Boolean(string='Order 7', default=False)
    
    def _default_category_id(self):
        if not self.env.registry.ready:
            return False
        tenant_id = self.env.user.tenant_id.id if self.env.user.tenant_id else False
        domain = [('tenant_id', '=', tenant_id)] if tenant_id else []
        cat = self.env['havanoposdesk.category'].sudo().search(domain + [('name', '=ilike', 'Basic')], limit=1)
        if not cat and tenant_id:
            cat = self.env['havanoposdesk.category'].sudo().search(domain, limit=1)
        if not cat:
            cat = self.env['havanoposdesk.category'].sudo().search([('name', '=ilike', 'Basic')], limit=1)
        return cat.id if cat else False

    def _default_uom_id(self):
        if not self.env.registry.ready:
            return False
        tenant_id = self.env.user.tenant_id.id if self.env.user.tenant_id else False
        domain = [('tenant_id', '=', tenant_id)] if tenant_id else []
        uom = self.env['havanoposdesk.uom'].sudo().search(domain + [('name', '=ilike', 'Each')], limit=1)
        if not uom and tenant_id:
            uom = self.env['havanoposdesk.uom'].sudo().search(domain, limit=1)
        if not uom:
            uom = self.env['havanoposdesk.uom'].sudo().search([('name', '=ilike', 'Each')], limit=1)
        return uom.id if uom else False

    category_id = fields.Many2one('havanoposdesk.category', string='Category', default=_default_category_id)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', default=_default_uom_id)
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id)
    currency_id = fields.Many2one(related='tenant_id.currency_id', string='Currency', store=False)
    advanced_price_ids = fields.One2many('havanoposdesk.product.uom.price', 'product_id', string='Advanced Prices')
    allow_advanced_pricing = fields.Boolean(related='tenant_id.allow_advanced_pricing', readonly=True)
    is_bundle = fields.Boolean(string='Is Bundle', default=False)
    bundle_item_ids = fields.One2many('havanoposdesk.product.bundle.item', 'parent_product_id', string='Bundle Items')

    @api.constrains('advanced_price_ids')
    def _check_advanced_price_ids_unique(self):
        for product in self:
            seen = set()
            for line in product.advanced_price_ids:
                key = (line.store_id.id, line.pricelist_id.id, line.uom_id.id)
                if key in seen:
                    store_name = line.store_id.name or ''
                    pricelist_name = line.pricelist_id.name or ''
                    uom_name = line.uom_id.name or ''
                    raise ValidationError(_(
                        "Cannot save product '%s': Duplicate price line found for Store '%s', Pricelist '%s', and Unit of Measure '%s'. At least one of Store, Pricelist, or UoM must be different."
                    ) % (product.name, store_name, pricelist_name, uom_name))
                seen.add(key)

    @api.depends('is_bundle', 'bundle_item_ids', 'bundle_item_ids.qty', 'bundle_item_ids.buying_price', 'bundle_item_ids.selling_price', 'bundle_item_ids.subtotal_cost', 'bundle_item_ids.subtotal_selling', 'uom_price_ids.price')
    def _compute_bundle_prices(self):
        for record in self:
            if record.is_bundle:
                record.buying_price = sum(item.subtotal_cost for item in record.bundle_item_ids)
                record.selling_price = sum(item.subtotal_selling for item in record.bundle_item_ids)
            elif record.id:
                default_store = self.env.user.default_store_id
                if not default_store and self.env.user.store_ids:
                    default_store = self.env.user.store_ids[0]
                if not default_store and record.store_ids:
                    default_store = record.store_ids[0]
                
                if default_store and default_store.pricelist_id:
                    price_line = record.uom_price_ids.filtered(
                        lambda p: p.store_id.id == default_store.id and p.pricelist_id.id == default_store.pricelist_id.id and (not record.uom_id or p.uom_id.id == record.uom_id.id)
                    )
                    if price_line:
                        record.selling_price = price_line[0].price

    def _inverse_selling_price(self):
        for record in self:
            if not record.is_bundle:
                default_store = self.env.user.default_store_id
                if not default_store and self.env.user.store_ids:
                    default_store = self.env.user.store_ids[0]
                if not default_store and record.store_ids:
                    default_store = record.store_ids[0]
                
                if default_store and default_store.pricelist_id:
                    price_line = record.uom_price_ids.filtered(
                        lambda p: p.store_id.id == default_store.id and p.pricelist_id.id == default_store.pricelist_id.id and (not record.uom_id or p.uom_id.id == record.uom_id.id)
                    )
                    if price_line:
                        price_line[0].price = record.selling_price

    @api.onchange('is_bundle', 'bundle_item_ids')
    def _onchange_bundle_item_ids(self):
        if self.is_bundle:
            self.track_qty = False
            self.opening_stock = 0.0
            self.buying_price = sum(
                item.subtotal_cost or ((item.qty or 0.0) * (item.buying_price or 0.0))
                for item in self.bundle_item_ids
            )
            self.selling_price = sum(
                item.subtotal_selling or ((item.qty or 0.0) * (item.selling_price or 0.0))
                for item in self.bundle_item_ids
            )


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

    @api.model
    def get_import_templates(self):
        return [{
            'label': _('Import Template for Products'),
            'template': '/havanoposdesk_odoo/static/src/data/product_import_template.csv'
        }]

    def action_export_with_inventory(self):
        """Export products with per-store pricing and inventory from advanced_price_ids.
        Uses Odoo-compatible relational headers so the CSV can be re-imported directly."""
        import io
        import csv
        import base64

        output = io.StringIO()
        writer = csv.writer(output)

        # Odoo-compatible relational headers for direct re-import
        writer.writerow([
            'name', 'item_code', 'barcode', 'buying_price',
            'category_id/name', 'uom_id/name', 'is_active',
            'advanced_price_ids/store_id/name', 'advanced_price_ids/pricelist_id/name',
            'advanced_price_ids/uom_id/name', 'advanced_price_ids/qty_to_be_sold',
            'advanced_price_ids/initial_stock', 'advanced_price_ids/price',
            'advanced_price_ids/on_hand_qty'
        ])

        products = self if self else self.search([('tenant_id', '=', self.env.user.tenant_id.id)])

        for product in products:
            price_lines = product.advanced_price_ids

            if price_lines:
                first = True
                for line in price_lines:
                    if first:
                        writer.writerow([
                            product.name, product.item_code or '', product.barcode or '',
                            product.buying_price,
                            product.category_id.name or '', product.uom_id.name or '',
                            1 if product.is_active else 0,
                            line.store_id.name or '', line.pricelist_id.name or '',
                            line.uom_id.name or '', line.qty_to_be_sold,
                            line.on_hand_qty, line.price,
                            line.on_hand_qty
                        ])
                        first = False
                    else:
                        writer.writerow([
                            '', '', '', '', '', '', '',
                            line.store_id.name or '', line.pricelist_id.name or '',
                            line.uom_id.name or '', line.qty_to_be_sold,
                            line.on_hand_qty, line.price,
                            line.on_hand_qty
                        ])
            else:
                # No price lines — export product row per store to show split inventory
                all_store_ids = set(product.store_ids.ids)
                valuations = self.env['havanoposdesk.stock.valuation'].search([
                    ('product_id', '=', product.id)
                ])
                for v in valuations:
                    if v.store_id:
                        all_store_ids.add(v.store_id.id)
                
                stores = self.env['havanoposdesk.store'].browse(list(all_store_ids))

                if not stores:
                    writer.writerow([
                        product.name, product.item_code or '', product.barcode or '',
                        product.buying_price,
                        product.category_id.name or '', product.uom_id.name or '',
                        1 if product.is_active else 0,
                        '', '', '', '', '', product.selling_price,
                        product.on_hand_qty
                    ])
                else:
                    first = True
                    for store in stores:
                        store_vals = valuations.filtered(lambda v: v.store_id.id == store.id)
                        on_hand = sum(store_vals.mapped('on_hand_qty'))
                        if first:
                            writer.writerow([
                                product.name, product.item_code or '', product.barcode or '',
                                product.buying_price,
                                product.category_id.name or '', product.uom_id.name or '',
                                1 if product.is_active else 0,
                                store.name, '', '', '', '', product.selling_price,
                                on_hand
                            ])
                            first = False
                        else:
                            writer.writerow([
                                '', '', '', '',
                                '', '', '',
                                store.name, '', '', '', '', '',
                                on_hand
                            ])

        csv_data = base64.b64encode(output.getvalue().encode('utf-8'))
        output.close()

        attachment = self.env['ir.attachment'].create({
            'name': 'products_with_inventory.csv',
            'type': 'binary',
            'datas': csv_data,
            'mimetype': 'text/csv',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'new',
        }

class HavanoposdeskProductCosting(models.Model):
    _name = 'havanoposdesk.product.costing'
    _description = 'Product Costing Table'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True, ondelete='cascade')
    purchase_line_id = fields.Many2one('havanoposdesk.purchase.line', string='Purchase Line', ondelete='cascade')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', related='product_id.tenant_id', store=True, index=True)
    date = fields.Date(string='Date', default=fields.Date.context_today)
    qty = fields.Float(string='Quantity')
    price = fields.Float(string='Price/Rate')
    cost_type = fields.Selection([('last', 'Last Purchase'), ('average', 'Average')], string='Cost Type', default='last')
