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
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')
    is_return = fields.Boolean(string='Is Return (Debit Note)', default=False)
    return_id = fields.Many2one('havanoposdesk.purchase', string='Original Purchase', copy=False)
    return_purchase_ids = fields.One2many('havanoposdesk.purchase', 'return_id', string='Returned Purchases')
    
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
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    seq_code = 'purch_ret' if vals.get('is_return') else 'purch'
                    vals['name'] = tenant._get_next_sequence(seq_code)
                else:
                    seq_name = 'havanoposdesk.purchase.return' if vals.get('is_return') else 'havanoposdesk.purchase'
                    vals['name'] = self.env['ir.sequence'].next_by_code(seq_name) or 'New'
        
        purchases = super().create(vals_list)
        
        for purchase in purchases:
            if purchase.state == 'posted':
                purchase.state = 'draft'
                purchase.action_post()
        return purchases

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft' and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted purchase. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed/posted purchase. Please cancel it first.")
        return super().unlink()

    def action_post(self):
        for purchase in self:
            if purchase.state != 'draft':
                continue
            for line in purchase.line_ids:
                if line.accepted_qty > 0:
                    if purchase.is_return:
                        # Revert/Subtract stock for return
                        line.product_id.sudo().opening_stock -= line.accepted_qty
                        
                        # Create Ledger Entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': 0.0,
                            'out_qty': line.accepted_qty,
                            'balance_qty': line.product_id.opening_stock,
                            'store': purchase.store_id.name if purchase.store_id else '',
                            'type': 'Purchase Return',
                            'doc_no': purchase.name,
                        })

                        # Update or Create Valuation Entry using sudo()
                        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                            ('product_id', '=', line.product_id.id),
                            ('store', '=', purchase.store_id.name if purchase.store_id else '')
                        ], limit=1)
                        
                        if valuation:
                            valuation.write({
                                'on_hand_qty': valuation.on_hand_qty - line.accepted_qty,
                            })
                        else:
                            self.env['havanoposdesk.stock.valuation'].sudo().create({
                                'product_id': line.product_id.id,
                                'store': purchase.store_id.name if purchase.store_id else '',
                                'on_hand_qty': -line.accepted_qty,
                            })
                    else:
                        # Normal Purchase
                        # Update Product On Hand (opening_stock) using sudo()
                        line.product_id.sudo().opening_stock += line.accepted_qty
                        
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
            purchase.write({'state': 'posted'})

    def action_cancel(self):
        for purchase in self:
            if purchase.state != 'posted':
                continue
            for line in purchase.line_ids:
                if line.accepted_qty > 0:
                    if purchase.is_return:
                        # Revert return: Add stock back using sudo()
                        line.product_id.sudo().opening_stock += line.accepted_qty
                        
                        # Create reverse ledger entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': line.accepted_qty,
                            'out_qty': 0.0,
                            'balance_qty': line.product_id.opening_stock,
                            'store': purchase.store_id.name if purchase.store_id else '',
                            'type': 'Purchase Return Cancelled',
                            'doc_no': purchase.name,
                        })

                        # Update Valuation Entry using sudo()
                        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                            ('product_id', '=', line.product_id.id),
                            ('store', '=', purchase.store_id.name if purchase.store_id else '')
                        ], limit=1)
                        if valuation:
                            valuation.write({
                                'on_hand_qty': valuation.on_hand_qty + line.accepted_qty,
                            })
                    else:
                        # Normal Purchase Cancelled
                        # Revert: Subtract stock using sudo()
                        line.product_id.sudo().opening_stock -= line.accepted_qty
                        
                        # Create reverse ledger entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': 0.0,
                            'out_qty': line.accepted_qty,
                            'balance_qty': line.product_id.opening_stock,
                            'store': purchase.store_id.name if purchase.store_id else '',
                            'type': 'Purchase Cancelled',
                            'doc_no': purchase.name,
                        })

                        # Update Valuation Entry using sudo()
                        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                            ('product_id', '=', line.product_id.id),
                            ('store', '=', purchase.store_id.name if purchase.store_id else '')
                        ], limit=1)
                        if valuation:
                            valuation.write({
                                'on_hand_qty': valuation.on_hand_qty - line.accepted_qty,
                            })
            purchase.write({'state': 'cancelled'})

    def action_draft(self):
        for purchase in self:
            if purchase.state != 'cancelled':
                continue
            purchase.write({'state': 'draft'})

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