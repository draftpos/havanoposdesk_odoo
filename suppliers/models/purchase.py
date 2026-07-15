from odoo.exceptions import ValidationError
from odoo import models, fields, api, _

class Purchase(models.Model):
    _name = 'havanoposdesk.purchase'
    _description = 'Purchase'

    def _default_posting_time(self):
        return 0.0

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    def _default_supplier_id(self):
        user = self.env.user
        tenant_id = user.tenant_id.id or self.env.context.get('default_tenant_id')
        if not tenant_id:
            tenant = self.env['havanoposdesk.tenant'].search([], limit=1)
            if not tenant:
                tenant = self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})
            tenant_id = tenant.id
            
        supplier = self.env['havanoposdesk.supplier'].search([
            ('name', '=', 'General'),
            ('tenant_id', '=', tenant_id)
        ], limit=1)
        if not supplier:
            store = self.env['havanoposdesk.store'].search([('tenant_id', '=', tenant_id)], limit=1)
            if not store:
                store = self.env['havanoposdesk.store'].create({
                    'name': 'Default Store',
                    'tenant_id': tenant_id
                })
            supplier = self.env['havanoposdesk.supplier'].create({
                'name': 'General',
                'tenant_id': tenant_id,
                'store_id': store.id
            })
        return supplier.id

    supplier = fields.Many2one('havanoposdesk.supplier', string='Supplier', required=True, default=_default_supplier_id)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id', store=True, readonly=False)
    allow_multi_currency = fields.Boolean(related='tenant_id.allow_multi_currency')

    @api.depends('store_id')
    def _compute_currency_id(self):
        for record in self:
            if record.store_id and not record.currency_id:
                record.currency_id = record.store_id.currency_id
    posting_date = fields.Datetime(string='Posting Date', default=fields.Datetime.now)
    
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amount_total', store=True)
    amount_tax = fields.Float(string='Taxes', compute='_compute_amount_total', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)
    
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    amount_total_base = fields.Float(string='Base Total', compute='_compute_amount_total_base', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')
    is_return = fields.Boolean(string='Is Return (Debit Note)', default=False)
    return_id = fields.Many2one('havanoposdesk.purchase', string='Original Purchase', copy=False)
    return_purchase_ids = fields.One2many('havanoposdesk.purchase', 'return_id', string='Returned Purchases')
    payment_status = fields.Selection([
        ('cash', 'Cash (Paid)'),
        ('account', 'On Account')
    ], string='Payment Status', default='account', required=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Payment Account', domain="[('type', 'in', ['Cash', 'Bank'])]")
    pos_payment_id = fields.Many2one('havanoposdesk.payment', string='POS Payment Batch')
    invoice_type = fields.Char(string='Type', compute='_compute_invoice_type', store=True)
    is_tax_enabled = fields.Boolean(related='tenant_id.enable_tax', string='Tax Enabled')

    @api.depends('is_return')
    def _compute_invoice_type(self):
        for record in self:
            record.invoice_type = 'Debit Note' if record.is_return else 'Purchase Invoice'
            
    line_ids = fields.One2many('havanoposdesk.purchase.line', 'purchase_id', string='Items')

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.amount')
    def _compute_amount_total(self):
        for record in self:
            record.amount_untaxed = sum(record.line_ids.mapped('price_subtotal'))
            record.amount_tax = sum(record.line_ids.mapped('price_tax'))
            record.amount_total = sum(record.line_ids.mapped('amount'))

    @api.depends('amount_total', 'currency_id', 'tenant_currency_id', 'posting_date')
    def _compute_amount_total_base(self):
        for record in self:
            if not record.currency_id or not record.tenant_currency_id or record.currency_id == record.tenant_currency_id:
                record.amount_total_base = record.amount_total
            else:
                date = record.posting_date or fields.Date.context_today(self)
                record.amount_total_base = record.currency_id._convert(
                    record.amount_total, record.tenant_currency_id, self.env.company, date
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))

            if vals.get('payment_status') == 'cash' and not vals.get('account_id'):
                raise ValidationError(_("Please specify a cash/bank payment account for cash purchases."))
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
            payment_status = vals.get('payment_status', record.payment_status)
            account_id = vals.get('account_id', record.account_id)
            if payment_status == 'cash' and not account_id:
                raise ValidationError("Please specify a cash/bank payment account for cash purchases.")
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
                
            # Auto-create payment if cash
            if purchase.payment_status == 'cash' and purchase.account_id:
                payment_type = 'receipt' if purchase.is_return else 'payment'
                
                existing_payment = self.env['havanoposdesk.payment'].search([
                    ('date', '=', fields.Date.context_today(self)),
                    ('reference', '=', 'POS Purchases'),
                    ('account_id', '=', purchase.account_id.id),
                    ('payment_type', '=', payment_type),
                    ('state', 'in', ['draft', 'posted']),
                ], limit=1)

                if existing_payment:
                    existing_payment.with_context(bypass_payment_check=True).write({'amount': existing_payment.amount + purchase.amount_total})
                    if existing_payment.state == 'posted':
                        if payment_type == 'receipt':
                            existing_payment.account_id.sudo().balance += purchase.amount_total_base
                        else:
                            existing_payment.account_id.sudo().balance -= purchase.amount_total_base
                    purchase.pos_payment_id = existing_payment.id
                else:
                    payment = self.env['havanoposdesk.payment'].create({
                        'payment_type': payment_type,
                        'partner_type': 'supplier',
                        'account_id': purchase.account_id.id,
                        'amount': purchase.amount_total,
                        'currency_id': purchase.currency_id.id,
                        'reference': 'POS Purchases',
                        'date': fields.Date.context_today(self),
                    })
                    payment.action_post()
                    purchase.pos_payment_id = payment.id

            for line in purchase.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                unit_rate = line.rate / line.uom_qty_multiplier if line.uom_qty_multiplier else line.rate
                if base_qty > 0:
                    if purchase.is_return:
                        # Revert/Subtract stock for return (no opening_stock update here)
                        
                        # Create Ledger Entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': 0.0,
                            'out_qty': base_qty,
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
                                'on_hand_qty': valuation.on_hand_qty - base_qty,
                            })
                        else:
                            self.env['havanoposdesk.stock.valuation'].sudo().create({
                                'product_id': line.product_id.id,
                                'store': purchase.store_id.name if purchase.store_id else '',
                                'on_hand_qty': -base_qty,
                            })
                    else:
                        # Normal Purchase
                        # Director's Custom Costing Logic:
                        # If quantity on hand is greater than 0, use the simple average (old_cost + new_cost) / 2
                        # If quantity on hand is 0 or less, use the new purchase cost directly
                        current_cost = line.product_id.buying_price or 0.0
                        current_qty = line.product_id.on_hand_qty or 0.0
                        
                        if current_qty > 0:
                            new_buying_price = (current_cost + unit_rate) / 2.0
                        else:
                            new_buying_price = unit_rate
                            
                        # Update buying_price (last updated value) using sudo()
                        line.product_id.sudo().write({
                            'buying_price': new_buying_price,
                            'cost_price': new_buying_price,
                        })
                        
                        # Create costing records in costing table
                        self.env['havanoposdesk.product.costing'].sudo().create({
                            'product_id': line.product_id.id,
                            'purchase_line_id': line.id,
                            'qty': base_qty,
                            'price': unit_rate,
                            'cost_type': 'last',
                            'date': purchase.posting_date,
                        })
                        
                        # Calculate and store average cost
                        # We use the properly weighted new_buying_price calculated above
                        self.env['havanoposdesk.product.costing'].sudo().create({
                            'product_id': line.product_id.id,
                            'purchase_line_id': line.id,
                            'qty': base_qty,
                            'price': new_buying_price,
                            'cost_type': 'average',
                            'date': purchase.posting_date,
                        })

                        # Create Ledger Entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': base_qty,
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
                                'on_hand_qty': valuation.on_hand_qty + base_qty,
                            })
                        else:
                            self.env['havanoposdesk.stock.valuation'].sudo().create({
                                'product_id': line.product_id.id,
                                'store': purchase.store_id.name if purchase.store_id else '',
                                'on_hand_qty': base_qty,
                            })
            purchase.write({'state': 'posted'})

    def action_cancel(self):
        for purchase in self:
            if purchase.state != 'posted':
                continue
                
            # Reverse POS Payment batch amounts and account balances
            if purchase.payment_status == 'cash' and purchase.pos_payment_id:
                payment = purchase.pos_payment_id
                payment_type = 'receipt' if purchase.is_return else 'payment'
                if payment.state == 'posted':
                    if payment_type == 'receipt':
                        payment.account_id.sudo().balance -= purchase.amount_total_base
                    else:
                        payment.account_id.sudo().balance += purchase.amount_total_base
                payment.with_context(bypass_payment_check=True).write({'amount': payment.amount - purchase.amount_total})

            # Remove costing records associated with this purchase's lines
            self.env['havanoposdesk.product.costing'].sudo().search([
                ('purchase_line_id', 'in', purchase.line_ids.ids)
            ]).unlink()

            for line in purchase.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                unit_rate = line.rate / line.uom_qty_multiplier if line.uom_qty_multiplier else line.rate
                if base_qty > 0:
                    if purchase.is_return:
                        # Revert return: Add stock back using sudo() (no opening_stock update)
                        
                        # Create reverse ledger entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': base_qty,
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
                                'on_hand_qty': valuation.on_hand_qty + base_qty,
                            })
                    else:
                        # Normal Purchase Cancelled
                        # Revert: Subtract stock using sudo() (no opening_stock update)
                        
                        # Revert product buying price to the previous purchase's rate (if any)
                        last_purchase = self.env['havanoposdesk.purchase.line'].search([
                            ('product_id', '=', line.product_id.id),
                            ('purchase_id.state', '=', 'posted'),
                            ('purchase_id', '!=', purchase.id)
                        ], order='id desc', limit=1)
                        if last_purchase:
                            last_rate = last_purchase.rate / last_purchase.uom_qty_multiplier if last_purchase.uom_qty_multiplier else last_purchase.rate
                            line.product_id.sudo().buying_price = last_rate

                        # Create reverse ledger entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': 0.0,
                            'out_qty': base_qty,
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
                                'on_hand_qty': valuation.on_hand_qty - base_qty,
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
    store_id = fields.Many2one(related='purchase_id.store_id', store=True)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Product Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', domain="[('tax_type', '=', 'Purchases'), ('active', '=', True)]")
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Float(string='Tax', compute='_compute_amount', store=True)
    amount = fields.Float(string='Total', compute='_compute_amount', store=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM')
    uom_qty_multiplier = fields.Float(string='UOM Multiplier', default=1.0)
    available_uom_ids = fields.Many2many('havanoposdesk.uom', compute='_compute_available_uom_ids', store=False)

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

    @api.depends('product_id')
    def _compute_available_uom_ids(self):
        for line in self:
            if not line.product_id:
                line.available_uom_ids = False
                continue
            
            uom_ids = line.product_id.uom_id.ids if line.product_id.uom_id else []
            prices = self.env['havanoposdesk.product.uom.price'].search([
                ('product_id', '=', line.product_id.id),
                ('pricelist_id.type', '=', 'buying')
            ])
            uom_ids.extend(prices.mapped('uom_id.id'))
            line.available_uom_ids = [(6, 0, list(set(uom_ids)))]

    @api.onchange('product_id', 'uom_id')
    def _onchange_product_uom(self):
        for line in self:
            if not line.product_id:
                line.uom_id = False
                line.uom_qty_multiplier = 1.0
                continue
                
            if not line.uom_id or line.uom_id.id not in line.available_uom_ids.ids:
                line.uom_id = line.product_id.uom_id
                
            line.tax_ids = [(6, 0, line.product_id.purchase_tax_ids.ids)]
            
            if line.uom_id == line.product_id.uom_id:
                line.rate = line.product_id.buying_price or line.product_id.cost_price or 0.0
                line.uom_qty_multiplier = 1.0
            else:
                price_record = self.env['havanoposdesk.product.uom.price'].search([
                    ('product_id', '=', line.product_id.id),
                    ('uom_id', '=', line.uom_id.id),
                    ('pricelist_id.type', '=', 'buying')
                ], limit=1)
                if price_record:
                    line.rate = price_record.price
                    line.uom_qty_multiplier = price_record.qty_to_be_sold
                else:
                    line.rate = line.product_id.buying_price or line.product_id.cost_price or 0.0
                    line.uom_qty_multiplier = 1.0

    @api.onchange('rate')
    def _onchange_rate(self):
        if self.tenant_id.restrict_price_modification and not self.env.user.has_group('havanoposdesk_odoo.group_tenant_admin'):
            self.rate = self._origin.rate if getattr(self, '_origin', False) else (self.product_id.buying_price if self.product_id else 0.0)
            return {
                'warning': {
                    'title': 'Price Modification Restricted',
                    'message': 'You cannot edit prices. Please contact the admin if you wish to change the price.'
                }
            }

