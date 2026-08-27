from odoo import models, fields, api, _
from datetime import datetime
from odoo.exceptions import ValidationError

class StockAdjustment(models.Model):
    _name = 'havanoposdesk.stock.adjustment'
    _description = 'Stock Adjustment'

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    external_ref = fields.Char(string='External Reference', copy=False, readonly=True, help="Reference from external POS system")
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    posting_date = fields.Datetime(string='Posting Date', default=fields.Datetime.now)
    allow_edit_date_time = fields.Boolean(string='Allow Edit Date & Time', default=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')
    
    fetch_all_data = fields.Boolean(string='Fetch All Items', default=True)
    fetch_category_id = fields.Many2one('havanoposdesk.category', string='Fetch Category Items')

    @api.model
    def _get_product_stock_on_hand(self, product, store):
        """Retrieve the current on-hand quantity for a product in a given store from stock valuation."""
        if not product:
            return 0.0
        
        store_rec = None
        store_name = ''
        if isinstance(store, models.Model) and store:
            store_rec = store
            store_name = store.name
        elif isinstance(store, int) and store:
            store_rec = self.env['havanoposdesk.store'].browse(store)
            store_name = store_rec.name if store_rec.exists() else ''
        elif isinstance(store, str) and store:
            store_name = store
            store_rec = self.env['havanoposdesk.store'].search([('name', '=', store)], limit=1)

        domain = [('product_id', '=', product.id)]
        if store_rec and store_name:
            domain.extend(['|', ('store_id', '=', store_rec.id), ('store', '=', store_name)])
        elif store_name:
            domain.append(('store', '=', store_name))
        elif store_rec:
            domain.append(('store_id', '=', store_rec.id))

        if hasattr(product, 'tenant_id') and product.tenant_id:
            domain.append(('tenant_id', '=', product.tenant_id.id))

        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search(domain, limit=1)
        return valuation.on_hand_qty if valuation else 0.0

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        store_id = res.get('store_id') or self._default_store_id()
        if store_id and 'store_id' not in res:
            res['store_id'] = store_id

        if res.get('fetch_all_data') and store_id:
            store = self.env['havanoposdesk.store'].browse(store_id)
            tenant_id = res.get('tenant_id') or self.env.user.tenant_id.id
            domain = [
                ('store_ids', 'in', [store_id]),
                ('track_qty', '=', True),
                ('is_bundle', '=', False),
                ('is_active', '=', True),
            ]
            if tenant_id:
                domain.append(('tenant_id', '=', tenant_id))

            products = self.env['havanoposdesk.product'].search(domain)
            lines = []
            for product in products:
                on_hand = self._get_product_stock_on_hand(product, store)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': on_hand,
                    'counted': on_hand,
                }))
            res['line_ids'] = lines
        return res
    
    line_ids = fields.One2many('havanoposdesk.stock.adjustment.line', 'adjustment_id', string='Items')
    total_qty_difference = fields.Float(
        string='Total Qty Difference',
        compute='_compute_totals',
        store=True
    )
    total_amount_difference = fields.Float(
        string='Total Amount Difference',
        compute='_compute_totals',
        store=True
    )

    @api.depends('line_ids.qty_difference', 'line_ids.amount_difference')
    def _compute_totals(self):
        for record in self:
            record.total_qty_difference = sum(record.line_ids.mapped('qty_difference'))
            record.total_amount_difference = sum(record.line_ids.mapped('amount_difference'))

    @api.onchange('fetch_all_data')
    def _onchange_fetch_all_data(self):
        if self.fetch_all_data:
            if not self.store_id:
                self.line_ids = [(5, 0, 0)]
                self.fetch_category_id = False
                return
            domain = [
                ('store_ids', 'in', [self.store_id.id]),
                ('track_qty', '=', True),
                ('is_bundle', '=', False),
                ('is_active', '=', True),
            ]
            if self.tenant_id:
                domain.append(('tenant_id', '=', self.tenant_id.id))
            products = self.env['havanoposdesk.product'].search(domain)
            lines = [(5, 0, 0)]
            for product in products:
                on_hand = self._get_product_stock_on_hand(product, self.store_id)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': on_hand,
                    'counted': on_hand,
                }))
            self.line_ids = lines
            self.fetch_category_id = False
        else:
            self.line_ids = [(5, 0, 0)]

    @api.onchange('fetch_category_id')
    def _onchange_fetch_category_id(self):
        if self.fetch_category_id:
            if not self.store_id:
                self.line_ids = [(5, 0, 0)]
                self.fetch_all_data = False
                return
            domain = [
                ('category_id', '=', self.fetch_category_id.id),
                ('store_ids', 'in', [self.store_id.id]),
                ('track_qty', '=', True),
                ('is_bundle', '=', False),
                ('is_active', '=', True),
            ]
            if self.tenant_id:
                domain.append(('tenant_id', '=', self.tenant_id.id))
            products = self.env['havanoposdesk.product'].search(domain)
            lines = [(5, 0, 0)]
            for product in products:
                on_hand = self._get_product_stock_on_hand(product, self.store_id)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': on_hand,
                    'counted': on_hand,
                }))
            self.line_ids = lines
            self.fetch_all_data = False

    @api.onchange('store_id')
    def _onchange_store_id(self):
        if not self.store_id:
            self.line_ids = [(5, 0, 0)]
            return

        if self.fetch_all_data or self.fetch_category_id:
            domain = [
                ('store_ids', 'in', [self.store_id.id]),
                ('track_qty', '=', True),
                ('is_bundle', '=', False),
                ('is_active', '=', True),
            ]
            if self.fetch_category_id:
                domain.append(('category_id', '=', self.fetch_category_id.id))
            if self.tenant_id:
                domain.append(('tenant_id', '=', self.tenant_id.id))
            
            products = self.env['havanoposdesk.product'].search(domain)
            lines = [(5, 0, 0)]
            for product in products:
                on_hand = self._get_product_stock_on_hand(product, self.store_id)
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': on_hand,
                    'counted': on_hand,
                }))
            self.line_ids = lines
        else:
            # Update on_hand for existing lines for the new store
            for line in self.line_ids:
                if line.product_id:
                    line.on_hand = self._get_product_stock_on_hand(line.product_id, self.store_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))

            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['name'] = tenant._get_next_sequence('stock_adj')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.stock.adjustment') or 'New'

            # Populate on_hand from stock valuation for manual adjustments
            if 'line_ids' in vals:
                store_id = vals.get('store_id')
                store = self.env['havanoposdesk.store'].browse(store_id) if store_id else False
                for line_cmd in vals['line_ids']:
                    if line_cmd[0] == 0:  # Create command (0, 0, {values})
                        line_vals = line_cmd[2]
                        product_id = line_vals.get('product_id')
                        if product_id and ('on_hand' not in line_vals or line_vals.get('on_hand') is None):
                            product = self.env['havanoposdesk.product'].browse(product_id)
                            if product:
                                line_vals['on_hand'] = self._get_product_stock_on_hand(product, store)
        
        return super().create(vals_list)

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft' and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted stock adjustment. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed/posted stock adjustment. Please cancel it first.")
        return super().unlink()

    def action_post(self):
        for adjustment in self:
            if adjustment.state != 'draft':
                continue
            is_creation = self.env.context.get('from_product_creation')
            for line in adjustment.line_ids:
                if not is_creation and line.qty_difference == 0.0:
                    continue
                # Do not modify opening_stock here anymore
                # Create Ledger Entry using sudo() to bypass access rights
                in_qty = line.counted if is_creation else (line.qty_difference if line.qty_difference > 0 else 0.0)
                out_qty = 0.0 if is_creation else (abs(line.qty_difference) if line.qty_difference < 0 else 0.0)
                
                self.env['havanoposdesk.stock.ledger'].sudo().create({
                    'product_id': line.product_id.id,
                    'in_qty': in_qty,
                    'out_qty': out_qty,
                    'balance_qty': line.counted,
                    'store': adjustment.store_id.name if adjustment.store_id else '',
                    'type': 'Opening Stock' if is_creation else 'Stock Adjustment',
                    'doc_no': adjustment.name,
                    'tenant_id': line.product_id.tenant_id.id,
                })

                # Update or Create Valuation Entry using sudo()
                val_domain = [('product_id', '=', line.product_id.id)]
                if adjustment.store_id:
                    val_domain.extend(['|', ('store_id', '=', adjustment.store_id.id), ('store', '=', adjustment.store_id.name)])
                if line.product_id.tenant_id:
                    val_domain.append(('tenant_id', '=', line.product_id.tenant_id.id))

                valuation = self.env['havanoposdesk.stock.valuation'].sudo().search(val_domain, limit=1)
                
                if valuation:
                    valuation.write({
                        'on_hand_qty': line.counted,
                        'store': adjustment.store_id.name if adjustment.store_id else valuation.store,
                    })
                else:
                    self.env['havanoposdesk.stock.valuation'].sudo().create({
                        'product_id': line.product_id.id,
                        'store': adjustment.store_id.name if adjustment.store_id else '',
                        'on_hand_qty': line.counted,
                        'tenant_id': line.product_id.tenant_id.id,
                    })
            adjustment.write({'state': 'posted'})

    def action_cancel(self):
        for adjustment in self:
            if adjustment.state != 'posted':
                continue
            
            # Check if this was an Opening Stock adjustment from product creation
            is_creation = bool(self.env['havanoposdesk.stock.ledger'].sudo().search([
                ('doc_no', '=', adjustment.name),
                ('type', '=', 'Opening Stock')
            ], limit=1))
            
            for line in adjustment.line_ids:
                if not is_creation and line.qty_difference == 0.0:
                    continue
                # Do not revert opening_stock anymore
                # Create Reverse Ledger Entry
                orig_ledger = self.env['havanoposdesk.stock.ledger'].sudo().search([
                    ('doc_no', '=', adjustment.name),
                    ('product_id', '=', line.product_id.id),
                    ('type', 'in', ['Opening Stock', 'Stock Adjustment'])
                ], limit=1)
                if orig_ledger:
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': orig_ledger.out_qty,
                        'out_qty': orig_ledger.in_qty,
                        'balance_qty': 0.0 if is_creation else line.on_hand,
                        'store': adjustment.store_id.name if adjustment.store_id else '',
                        'type': 'Adjustment Cancelled',
                        'doc_no': adjustment.name,
                        'tenant_id': line.product_id.tenant_id.id,
                    })

                # Update Valuation Entry
                val_domain = [('product_id', '=', line.product_id.id)]
                if adjustment.store_id:
                    val_domain.extend(['|', ('store_id', '=', adjustment.store_id.id), ('store', '=', adjustment.store_id.name)])
                if line.product_id.tenant_id:
                    val_domain.append(('tenant_id', '=', line.product_id.tenant_id.id))

                valuation = self.env['havanoposdesk.stock.valuation'].sudo().search(val_domain, limit=1)
                if valuation:
                    valuation.write({
                        'on_hand_qty': 0.0 if is_creation else line.on_hand,
                    })
            adjustment.write({'state': 'cancelled'})

    def action_draft(self):
        for adjustment in self:
            if adjustment.state != 'cancelled':
                continue
            for line in adjustment.line_ids:
                line.on_hand = adjustment._get_product_stock_on_hand(line.product_id, adjustment.store_id)
            adjustment.write({'state': 'draft'})

class StockAdjustmentLine(models.Model):
    _name = 'havanoposdesk.stock.adjustment.line'
    _description = 'Stock Adjustment Line'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    adjustment_id = fields.Many2one('havanoposdesk.stock.adjustment', string='Stock Adjustment', required=True, ondelete='cascade')
    store_id = fields.Many2one(related='adjustment_id.store_id', store=True, readonly=True)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Product Code', readonly=True)
    on_hand = fields.Float(string='On Hand', readonly=True)
    counted = fields.Float(string='Counted')
    buying_price = fields.Float(related='product_id.buying_price', string='Cost price', readonly=True, store=True)
    qty_difference = fields.Float(string='Qty Difference', compute='_compute_differences', store=True)
    amount_difference = fields.Float(string='Amount Difference', compute='_compute_differences', store=True)

    @api.depends('counted', 'on_hand', 'buying_price')
    def _compute_differences(self):
        for record in self:
            record.qty_difference = record.counted - record.on_hand
            record.amount_difference = record.qty_difference * record.buying_price

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            store = self.adjustment_id.store_id or self.store_id
            if not store and self.env.context.get('default_store_id'):
                store = self.env['havanoposdesk.store'].browse(self.env.context.get('default_store_id'))
            if not store:
                store = self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1)
            
            on_hand = self.env['havanoposdesk.stock.adjustment']._get_product_stock_on_hand(self.product_id, store)
            self.on_hand = on_hand
            self.counted = on_hand
