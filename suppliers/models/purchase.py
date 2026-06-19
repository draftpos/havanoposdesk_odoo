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
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    supplier = fields.Many2one('havanoposdesk.supplier', string='Supplier', required=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amount_total', store=True)
    amount_tax = fields.Float(string='Taxes', compute='_compute_amount_total', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)
    
    line_ids = fields.One2many('havanoposdesk.purchase.line', 'purchase_id', string='Items')

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.amount')
    def _compute_amount_total(self):
        for record in self:
            record.amount_untaxed = sum(record.line_ids.mapped('price_subtotal'))
            record.amount_tax = sum(record.line_ids.mapped('price_tax'))
            record.amount_total = sum(record.line_ids.mapped('amount'))

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

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    purchase_id = fields.Many2one('havanoposdesk.purchase', string='Purchase', required=True, ondelete='cascade')
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Item Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', domain="[('tax_type', '=', 'Purchases'), ('active', '=', True)]")
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Float(string='Tax', compute='_compute_amount', store=True)
    amount = fields.Float(string='Total', compute='_compute_amount', store=True)

    @api.depends('accepted_qty', 'rate', 'tax_ids')
    def _compute_amount(self):
        for record in self:
            base_amount = record.accepted_qty * record.rate
            taxes = record.tax_ids
            
            inclusive_taxes = taxes.filtered(lambda t: t.is_inclusive)
            exclusive_taxes = taxes.filtered(lambda t: not t.is_inclusive)
            
            rate_incl = sum(inclusive_taxes.mapped('rate')) / 100.0
            rate_excl = sum(exclusive_taxes.mapped('rate')) / 100.0
            
            untaxed_amount = base_amount / (1.0 + rate_incl)
            inclusive_tax_amount = base_amount - untaxed_amount
            exclusive_tax_amount = untaxed_amount * rate_excl
            
            record.price_subtotal = untaxed_amount
            record.price_tax = inclusive_tax_amount + exclusive_tax_amount
            record.amount = record.price_subtotal + record.price_tax

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.rate = self.product_id.buying_price
            self.tax_ids = [(6, 0, self.product_id.purchase_tax_ids.ids)]