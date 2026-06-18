from odoo import models, fields, api

class Purchase(models.Model):
    _name = 'havanoposdesk.purchase'
    _description = 'Purchase'

    def _default_posting_time(self):
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        return now_local.hour + now_local.minute / 60.0

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    supplier = fields.Many2one('havanoposdesk.supplier', string='Supplier', required=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    
    line_ids = fields.One2many('havanoposdesk.purchase.line', 'purchase_id', string='Items')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.purchase') or 'New'
        
        purchases = super().create(vals_list)
        
        for purchase in purchases:
            for line in purchase.line_ids:
                if line.accepted_qty > 0:
                    # Update Product On Hand (opening_stock)
                    line.product_id.opening_stock += line.accepted_qty
                    
                    # Create Ledger Entry using sudo()
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': line.accepted_qty,
                        'out_qty': 0.0,
                        'balance_qty': line.product_id.opening_stock,
                        'store': purchase.store_id.name if purchase.store_id else '',
                        'type': 'Purchase',
                        'doc_no': purchase.name,
                    })

                    # Update or Create Valuation Entry using sudo()
                    valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', purchase.store_id.name if purchase.store_id else '')
                    ], limit=1)
                    
                    if valuation:
                        valuation.write({
                            'on_hand_qty': valuation.on_hand_qty + line.accepted_qty,
                        })
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': purchase.store_id.name if purchase.store_id else '',
                            'on_hand_qty': line.accepted_qty,
                        })
        return purchases

class PurchaseLine(models.Model):
    _name = 'havanoposdesk.purchase.line'
    _description = 'Purchase Line'

    purchase_id = fields.Many2one('havanoposdesk.purchase', string='Purchase', required=True, ondelete='cascade')
    product_id = fields.Many2one('havanoposdesk.product', string='Item Name', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Item Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    amount = fields.Float(string='Amount', compute='_compute_amount', store=True)

    @api.depends('accepted_qty', 'rate')
    def _compute_amount(self):
        for record in self:
            record.amount = record.accepted_qty * record.rate

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.rate = self.product_id.buying_price