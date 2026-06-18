from odoo import models, fields, api

class StockValuation(models.Model):
    _name = 'havanoposdesk.stock.valuation'
    _description = 'Stock Valuation'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True)
    item_name = fields.Char(related='product_id.name', string='Item Name', store=True)
    item_code = fields.Char(related='product_id.item_code', string='Code', store=True)
    category_id = fields.Many2one(related='product_id.category_id', string='Category', store=True)
    store = fields.Char(string='Store')
    on_hand_qty = fields.Float(string='On Hand Qty')
    value_cost = fields.Float(string='Value Cost', compute='_compute_valuation_amounts', store=True)
    value_selling = fields.Float(string='Value Selling', compute='_compute_valuation_amounts', store=True)

    @api.depends('on_hand_qty', 'product_id.buying_price', 'product_id.selling_price')
    def _compute_valuation_amounts(self):
        for record in self:
            record.value_cost = record.on_hand_qty * record.product_id.buying_price
            record.value_selling = record.on_hand_qty * record.product_id.selling_price

class StockLedger(models.Model):
    _name = 'havanoposdesk.stock.ledger'
    _description = 'Stock Ledger'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True)
    item_name = fields.Char(related='product_id.name', string='Item Name', store=True)
    item_code = fields.Char(related='product_id.item_code', string='Code', store=True)
    uom_id = fields.Many2one(related='product_id.uom_id', string='UOM', store=True)
    in_qty = fields.Float(string='In Qty')
    out_qty = fields.Float(string='Out Qty')
    balance_qty = fields.Float(string='Balance Qty')
    store = fields.Char(string='Store')
    category_id = fields.Many2one(related='product_id.category_id', string='Item Category', store=True)
    in_value = fields.Float(string='In Value', compute='_compute_values', store=True)
    out_value = fields.Float(string='Out Value', compute='_compute_values', store=True)
    buying_price = fields.Float(related='product_id.buying_price', string='Buying Price', store=True, readonly=True)
    type = fields.Char(string='Type')
    doc_no = fields.Char(string='Doc No')
    balance_value = fields.Float(string='Balance Value', compute='_compute_values', store=True)

    @api.depends('in_qty', 'out_qty', 'balance_qty', 'buying_price', 'product_id.buying_price')
    def _compute_values(self):
        for record in self:
            buying_price = record.buying_price or record.product_id.buying_price or 0.0
            record.in_value = record.in_qty * buying_price
            record.out_value = record.out_qty * buying_price
            record.balance_value = record.balance_qty * buying_price

