from odoo import models, fields, api

class Sale(models.Model):
    _name = 'havanoposdesk.sale'
    _description = 'Sale'

    def _default_posting_time(self):
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        return now_local.hour + now_local.minute / 60.0

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    customer = fields.Many2one('havanoposdesk.customer', string='Customer', required=True)
    store = fields.Char(string='Store')
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    
    line_ids = fields.One2many('havanoposdesk.sale.line', 'sale_id', string='Items')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale') or 'New'
        
        sales = super().create(vals_list)
        
        for sale in sales:
            for line in sale.line_ids:
                if line.accepted_qty > 0:
                    # Update Product On Hand (opening_stock)
                    line.product_id.opening_stock -= line.accepted_qty
                    
                    # Create Ledger Entry using sudo()
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': 0.0,
                        'out_qty': line.accepted_qty,
                        'balance_qty': line.product_id.opening_stock,
                        'store': sale.store,
                        'type': 'Sale',
                        'doc_no': sale.name,
                    })

                    # Update or Create Valuation Entry using sudo()
                    valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', sale.store)
                    ], limit=1)
                    
                    if valuation:
                        valuation.write({
                            'on_hand_qty': valuation.on_hand_qty - line.accepted_qty,
                        })
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': sale.store,
                            'on_hand_qty': -line.accepted_qty,
                        })
        return sales

class SaleLine(models.Model):
    _name = 'havanoposdesk.sale.line'
    _description = 'Sale Line'

    sale_id = fields.Many2one('havanoposdesk.sale', string='Sale', required=True, ondelete='cascade')
    product_id = fields.Many2one('havanoposdesk.product', string='Item Name', required=True)
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
            self.rate = self.product_id.selling_price
