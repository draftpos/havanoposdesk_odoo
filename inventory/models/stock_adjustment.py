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
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    allow_edit_date_time = fields.Boolean(string='Allow Edit Date & Time', default=False)
    
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
                    'counted': 0.0,
                }))
            res['line_ids'] = lines
        return res
    
    line_ids = fields.One2many('havanoposdesk.stock.adjustment.line', 'adjustment_id', string='Items')

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
                    'counted': 0.0,
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
                    'counted': 0.0,
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
                        'counted': 0.0,
                    }))
                self.line_ids = lines

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.stock.adjustment') or 'New'
        
        adjustments = super().create(vals_list)
        
        for adjustment in adjustments:
            for line in adjustment.line_ids:
                if line.qty_difference != 0:
                    # Update Product On Hand (opening_stock)
                    line.product_id.opening_stock = line.counted
                    
                    # Create Ledger Entry using sudo() to bypass access rights
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': line.qty_difference if line.qty_difference > 0 else 0.0,
                        'out_qty': abs(line.qty_difference) if line.qty_difference < 0 else 0.0,
                        'balance_qty': line.counted,
                        'store': adjustment.store_id.name if adjustment.store_id else '',
                        'type': 'Stock Adjustment',
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
        return adjustments

class StockAdjustmentLine(models.Model):
    _name = 'havanoposdesk.stock.adjustment.line'
    _description = 'Stock Adjustment Line'

    adjustment_id = fields.Many2one('havanoposdesk.stock.adjustment', string='Stock Adjustment', required=True, ondelete='cascade')
    product_id = fields.Many2one('havanoposdesk.product', string='Item Name', required=True)
    on_hand = fields.Float(string='On Hand', readonly=True)
    counted = fields.Float(string='Counted')
    buying_price = fields.Float(related='product_id.buying_price', string='Buy price', readonly=True, store=True)
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
