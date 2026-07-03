from odoo import models, fields, api
from datetime import datetime

class StockAdjustment(models.Model):
    _name = 'havanoposdesk.stock.adjustment'
    _description = 'Stock Adjustment'

    def _default_posting_time(self):
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        return now_local.hour + now_local.minute / 60.0

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    allow_edit_date_time = fields.Boolean(string='Allow Edit Date & Time', default=False)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')
    
    fetch_all_data = fields.Boolean(string='Fetch All Items', default=True)
    fetch_category_id = fields.Many2one('havanoposdesk.category', string='Fetch Category Items')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if res.get('fetch_all_data'):
            store_id = res.get('store_id')
            domain = [('store_id', '=', store_id)] if store_id else []
            products = self.env['havanoposdesk.product'].search(domain)
            lines = []
            for product in products:
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': product.opening_stock,
                    'counted': product.opening_stock,
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
            domain = [('store_id', '=', self.store_id.id)] if self.store_id else []
            products = self.env['havanoposdesk.product'].search(domain)
            lines = [(5, 0, 0)]
            for product in products:
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': product.opening_stock,
                    'counted': product.opening_stock,
                }))
            self.line_ids = lines
            self.fetch_category_id = False

    @api.onchange('fetch_category_id')
    def _onchange_fetch_category_id(self):
        if self.fetch_category_id:
            domain = [('category_id', '=', self.fetch_category_id.id)]
            if self.store_id:
                domain.append(('store_id', '=', self.store_id.id))
            products = self.env['havanoposdesk.product'].search(domain)
            lines = [(5, 0, 0)]
            for product in products:
                lines.append((0, 0, {
                    'product_id': product.id,
                    'on_hand': product.opening_stock,
                    'counted': product.opening_stock,
                }))
            self.line_ids = lines
            self.fetch_all_data = False

    @api.onchange('store_id')
    def _onchange_store_id(self):
        if self.store_id:
            domain = [('store_id', '=', self.store_id.id)]
            if self.fetch_category_id:
                domain.append(('category_id', '=', self.fetch_category_id.id))
            
            if self.fetch_all_data or self.fetch_category_id:
                products = self.env['havanoposdesk.product'].search(domain)
                lines = [(5, 0, 0)]
                for product in products:
                    lines.append((0, 0, {
                        'product_id': product.id,
                        'on_hand': product.opening_stock,
                        'counted': product.opening_stock,
                    }))
                self.line_ids = lines

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['name'] = tenant._get_next_sequence('stock_adj')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.stock.adjustment') or 'New'

            # Populate on_hand from product opening_stock for manual adjustments
            if 'line_ids' in vals:
                for line_cmd in vals['line_ids']:
                    if line_cmd[0] == 0:  # Create command (0, 0, {values})
                        line_vals = line_cmd[2]
                        product_id = line_vals.get('product_id')
                        if product_id and not line_vals.get('on_hand'):
                            product = self.env['havanoposdesk.product'].browse(product_id)
                            if product:
                                line_vals['on_hand'] = product.opening_stock
        
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
                # Update Product On Hand (opening_stock)
                if not is_creation:
                    line.product_id.opening_stock = line.counted
                
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
                })

                # Update or Create Valuation Entry using sudo()
                valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('store', '=', adjustment.store_id.name if adjustment.store_id else '')
                ], limit=1)
                
                if valuation:
                    valuation.write({
                        'on_hand_qty': line.counted,
                    })
                else:
                    self.env['havanoposdesk.stock.valuation'].sudo().create({
                        'product_id': line.product_id.id,
                        'store': adjustment.store_id.name if adjustment.store_id else '',
                        'on_hand_qty': line.counted,
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
                # Revert Product On Hand (opening_stock)
                if is_creation:
                    line.product_id.opening_stock = 0.0
                else:
                    line.product_id.opening_stock = line.on_hand
                
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
                        'balance_qty': line.product_id.opening_stock,
                        'store': adjustment.store_id.name if adjustment.store_id else '',
                        'type': 'Adjustment Cancelled',
                        'doc_no': adjustment.name,
                    })

                # Update Valuation Entry
                valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('store', '=', adjustment.store_id.name if adjustment.store_id else '')
                ], limit=1)
                if valuation:
                    valuation.write({
                        'on_hand_qty': line.product_id.opening_stock,
                    })
            adjustment.write({'state': 'cancelled'})

    def action_draft(self):
        for adjustment in self:
            if adjustment.state != 'cancelled':
                continue
            for line in adjustment.line_ids:
                line.on_hand = line.product_id.opening_stock
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
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Item Code', readonly=True)
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
            self.on_hand = self.product_id.opening_stock
            self.counted = 0.0
