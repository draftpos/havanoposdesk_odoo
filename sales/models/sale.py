from odoo import models, fields, api, _
from datetime import datetime, time
from odoo.exceptions import ValidationError

class Sale(models.Model):
    _name = 'havanoposdesk.sale'
    _description = 'Sale'
    _order = 'date desc, id desc'

    _sql_constraints = [
        ('local_invoice_id_tenant_uniq', 'unique(local_invoice_id, tenant_id)', 'The Local Invoice ID must be unique per tenant!')
    ]

    def _default_posting_time(self):
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        return now_local.hour + now_local.minute / 60.0

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    customer = fields.Many2one('havanoposdesk.customer', string='Customer', required=True)
    store = fields.Char(string='Store')
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    local_invoice_id = fields.Char(string='Local Invoice ID', copy=False)
    
    is_return = fields.Boolean(string='Is Credit Note', default=False)
    return_id = fields.Many2one('havanoposdesk.sale', string='Original Sale')
    return_sale_ids = fields.One2many('havanoposdesk.sale', 'return_id', string='Credit Notes')
    invoice_type = fields.Char(string='Type', compute='_compute_invoice_type', store=True)

    @api.constrains('local_invoice_id', 'tenant_id')
    def _check_local_invoice_id_uniqueness(self):
        for sale in self:
            if sale.local_invoice_id:
                duplicate = self.search([
                    ('tenant_id', '=', sale.tenant_id.id),
                    ('local_invoice_id', '=', sale.local_invoice_id),
                    ('id', '!=', sale.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("The Local Invoice ID must be unique per tenant!"))

    @api.depends('is_return')
    def _compute_invoice_type(self):
        for record in self:
            record.invoice_type = 'Credit Note' if record.is_return else 'Sales Invoice'
    
    def _default_account_id(self):
        return self.env['havanoposdesk.account'].search([('type', 'in', ['Cash', 'Bank'])], limit=1).id

    payment_status = fields.Selection([
        ('cash', 'Cash (Paid)'),
        ('account', 'On Account')
    ], string='Payment Status', default='cash', required=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Deposit Account', domain="[('type', 'in', ['Cash', 'Bank'])]", default=_default_account_id)
    pos_payment_id = fields.Many2one('havanoposdesk.payment', string='POS Payment Batch')
    payment_ids = fields.Many2many('havanoposdesk.payment', compute='_compute_payment_ids', string='Payments')

    @api.depends('pos_payment_id')
    def _compute_payment_ids(self):
        for record in self:
            record.payment_ids = [(6, 0, [record.pos_payment_id.id])] if record.pos_payment_id else False
    
    line_ids = fields.One2many('havanoposdesk.sale.line', 'sale_id', string='Items')

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    # View-required fields to avoid undefined errors
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one(
        'havanoposdesk.store', 
        string='Store', 
        required=True, 
        default=_default_store_id
    )
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_currency_id', store=True, readonly=False)
    allow_multi_currency = fields.Boolean(related='tenant_id.allow_multi_currency')

    @api.depends('store_id')
    def _compute_currency_id(self):
        for record in self:
            if record.store_id and not record.currency_id:
                record.currency_id = record.store_id.currency_id
    terminal_id = fields.Many2one(
        'havanoposdesk.pos.terminal', 
        string='POS Terminal', 
        default=lambda self: self.env.user.selected_terminal_id.id if self.env.user.selected_terminal_id else False
    )
    date = fields.Datetime(string='Sale Date', default=fields.Datetime.now, required=True)
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amount_total', store=True)
    amount_tax = fields.Float(string='Taxes', compute='_compute_amount_total', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)
    
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    amount_total_base = fields.Float(string='Base Total', compute='_compute_amount_total_base', store=True)
    
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user.id)
    is_tax_enabled = fields.Boolean(related='tenant_id.enable_tax', string='Tax Enabled')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True)

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.amount')
    def _compute_amount_total(self):
        for record in self:
            record.amount_untaxed = sum(record.line_ids.mapped('price_subtotal'))
            record.amount_tax = sum(record.line_ids.mapped('price_tax'))
            record.amount_total = sum(record.line_ids.mapped('amount'))

    @api.depends('amount_total', 'currency_id', 'tenant_currency_id', 'date')
    def _compute_amount_total_base(self):
        for record in self:
            if not record.currency_id or not record.tenant_currency_id or record.currency_id == record.tenant_currency_id:
                record.amount_total_base = record.amount_total
            else:
                date = record.date or fields.Date.context_today(self)
                record.amount_total_base = record.currency_id._convert(
                    record.amount_total, record.tenant_currency_id, self.env.company, date
                )

    @api.depends('line_ids.cost_price', 'line_ids.accepted_qty', 'is_return')
    def _compute_total_cost(self):
        for record in self:
            sign = -1.0 if record.is_return else 1.0
            record.total_cost = sum(line.cost_price * line.accepted_qty for line in record.line_ids) * sign

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
                    if vals.get('is_return'):
                        vals['name'] = tenant._get_next_sequence('sale_ret')
                    else:
                        vals['name'] = tenant._get_next_sequence('sale')
                else:
                    if vals.get('is_return'):
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale.return') or 'New'
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale') or 'New'
            
            # Default account_id for cash sales if not provided
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if vals.get('payment_status', 'cash') == 'cash' and not vals.get('account_id'):
                domain = [('type', 'in', ['Cash', 'Bank'])]
                if tenant_id:
                    domain.append(('tenant_id', '=', tenant_id))
                account = self.env['havanoposdesk.account'].search(domain, limit=1)
                if account:
                    vals['account_id'] = account.id
            
            # Sync store and store_id
            if 'store' in vals and not vals.get('store_id'):
                domain = [('name', '=', vals['store'])]
                if tenant_id:
                    domain.append(('tenant_id', '=', tenant_id))
                store = self.env['havanoposdesk.store'].search(domain, limit=1)
                if store:
                    vals['store_id'] = store.id
            elif 'store_id' in vals and not vals.get('store'):
                store = self.env['havanoposdesk.store'].browse(vals['store_id'])
                if store:
                    vals['store'] = store.name
                    
            # Sync date and posting_date / posting_time
            if 'date' in vals and not vals.get('posting_date'):
                dt = fields.Datetime.to_datetime(vals['date'])
                vals['posting_date'] = dt.date()
                vals['posting_time'] = dt.hour + dt.minute / 60.0
            elif 'posting_date' in vals and not vals.get('date'):
                p_date = fields.Date.to_date(vals['posting_date'])
                p_time = vals.get('posting_time', 0.0)
                hours = int(p_time)
                minutes = int((p_time - hours) * 60)
                vals['date'] = datetime.combine(p_date, time(hours, minutes))

        sales = super().create(vals_list)
        
        for sale in sales:
            if sale.state in ['confirmed', 'done']:
                # Set to draft temporarily to let action_post execute
                sale.state = 'draft'
                sale.action_post()
        return sales

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft' and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed sale. Please cancel it first.")

        # Sync values on write
        if 'store' in vals and 'store_id' not in vals:
            for record in self:
                domain = [('name', '=', vals['store'])]
                if record.tenant_id:
                    domain.append(('tenant_id', '=', record.tenant_id.id))
                store = self.env['havanoposdesk.store'].search(domain, limit=1)
                if store:
                    vals['store_id'] = store.id
                break # Only checking first record's tenant is usually sufficient for batch writes of the same store
        elif 'store_id' in vals and 'store' not in vals:
            store = self.env['havanoposdesk.store'].browse(vals['store_id'])
            if store:
                vals['store'] = store.name

        if 'date' in vals and 'posting_date' not in vals:
            dt = fields.Datetime.to_datetime(vals['date'])
            vals['posting_date'] = dt.date()
            vals['posting_time'] = dt.hour + dt.minute / 60.0
        elif 'posting_date' in vals and 'date' not in vals:
            p_date = fields.Date.to_date(vals['posting_date'])
            p_time = vals.get('posting_time') or (self.posting_time if hasattr(self, 'posting_time') else 0.0)
            hours = int(p_time)
            minutes = int((p_time - hours) * 60)
            vals['date'] = datetime.combine(p_date, time(hours, minutes))

        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed sale. Please cancel it first.")
        return super().unlink()

    def action_post(self):
        for sale in self:
            if sale.state != 'draft':
                continue
            
            # Auto-create payment if cash
            if sale.payment_status == 'cash' and sale.account_id:
                payment_type = 'payment' if sale.is_return else 'receipt'
                
                existing_payment = self.env['havanoposdesk.payment'].search([
                    ('tenant_id', '=', sale.tenant_id.id),
                    ('date', '=', fields.Date.context_today(self)),
                    ('reference', '=', 'POS Payments'),
                    ('account_id', '=', sale.account_id.id),
                    ('payment_type', '=', payment_type),
                    ('state', 'in', ['draft', 'posted']),
                ], limit=1)

                if existing_payment:
                    existing_payment.with_context(bypass_payment_check=True).write({'amount': existing_payment.amount + abs(sale.amount_total)})
                    if existing_payment.state == 'posted':
                        existing_payment.account_id.sudo().balance += sale.amount_total_base
                    sale.pos_payment_id = existing_payment.id
                else:
                    payment = self.env['havanoposdesk.payment'].create({
                        'payment_type': payment_type,
                        'partner_type': 'customer',
                        'account_id': sale.account_id.id,
                        'amount': abs(sale.amount_total),
                        'currency_id': sale.currency_id.id,
                        'reference': 'POS Payments',
                        'date': fields.Date.context_today(self),
                        'tenant_id': sale.tenant_id.id,
                    })
                    payment.action_post()
                    sale.pos_payment_id = payment.id

            for line in sale.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                if base_qty > 0:
                    valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', sale.store)
                    ], limit=1)
                    
                    current_qty = valuation.on_hand_qty if valuation else 0.0
                    if sale.is_return:
                        new_balance = current_qty + base_qty
                    else:
                        new_balance = current_qty - base_qty

                    if valuation:
                        valuation.write({'on_hand_qty': new_balance})
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': sale.store,
                            'on_hand_qty': new_balance,
                            'tenant_id': line.product_id.tenant_id.id,
                        })

                    if sale.is_return:
                        # Add back to stock
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': base_qty,
                            'out_qty': 0.0,
                            'balance_qty': new_balance,
                            'buying_price': line.cost_price / line.uom_qty_multiplier if line.uom_qty_multiplier else line.cost_price,
                            'store': sale.store,
                            'type': 'Credit Note',
                            'doc_no': sale.name,
                            'tenant_id': line.product_id.tenant_id.id,
                        })
                    else:
                        # Update selling_price, and buying_price
                        line.product_id.sudo().write({
                            'selling_price': line.rate,
                            'buying_price': line.cost_price / line.uom_qty_multiplier if line.uom_qty_multiplier else line.cost_price,
                        })
                        
                        # Create Ledger Entry using sudo()
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': line.product_id.id,
                            'in_qty': 0.0,
                            'out_qty': base_qty,
                            'balance_qty': new_balance,
                            'buying_price': line.cost_price / line.uom_qty_multiplier if line.uom_qty_multiplier else line.cost_price,
                            'store': sale.store,
                            'type': 'Sale',
                            'doc_no': sale.name,
                            'tenant_id': line.product_id.tenant_id.id,
                        })
                elif base_qty < 0:
                    valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', sale.store)
                    ], limit=1)
                    
                    current_qty = valuation.on_hand_qty if valuation else 0.0
                    if sale.is_return:
                        new_balance = current_qty + base_qty
                    else:
                        new_balance = current_qty - base_qty

                    if valuation:
                        valuation.write({'on_hand_qty': new_balance})
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': sale.store,
                            'on_hand_qty': new_balance,
                            'tenant_id': line.product_id.tenant_id.id,
                        })

                    # Return sale: add back to stock
                    # Create Ledger Entry using sudo()
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': abs(base_qty),
                        'out_qty': 0.0,
                        'balance_qty': new_balance,
                        'store': sale.store,
                        'type': 'Return',
                        'doc_no': sale.name,
                        'tenant_id': line.product_id.tenant_id.id,
                    })
            sale.write({'state': 'done'})

    def action_cancel(self):
        for sale in self:
            if sale.state not in ['confirmed', 'done']:
                continue
            
            for line in sale.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                # Create reverse ledger entry using sudo()
                orig_ledgers = self.env['havanoposdesk.stock.ledger'].sudo().search([
                    ('doc_no', '=', sale.name),
                    ('product_id', '=', line.product_id.id),
                    ('type', 'in', ['Sale', 'Return', 'Credit Note'])
                ])
                for orig_ledger in orig_ledgers:
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': orig_ledger.out_qty,
                        'out_qty': orig_ledger.in_qty,
                        'balance_qty': line.product_id.opening_stock,
                        'buying_price': orig_ledger.buying_price,
                        'store': sale.store,
                        'type': 'Sale Cancelled',
                        'doc_no': sale.name,
                    })

                # Update Valuation Entry using sudo()
                valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('store', '=', sale.store)
                ], limit=1)
                if valuation:
                    if sale.is_return:
                        valuation.write({'on_hand_qty': valuation.on_hand_qty - base_qty})
                    else:
                        valuation.write({'on_hand_qty': valuation.on_hand_qty + base_qty})

            # Reverse POS Payment batch amounts and account balances
            if sale.payment_status == 'cash' and sale.pos_payment_id:
                payment = sale.pos_payment_id
                if payment.state == 'posted':
                    payment.account_id.sudo().balance -= sale.amount_total_base
                payment.with_context(bypass_payment_check=True).write({'amount': payment.amount - abs(sale.amount_total)})
                
            sale.write({'state': 'cancelled'})

    def action_draft(self):
        for sale in self:
            if sale.state != 'cancelled':
                continue
            sale.write({'state': 'draft'})

class SaleLine(models.Model):
    _name = 'havanoposdesk.sale.line'
    _description = 'Sale Line'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    sale_id = fields.Many2one('havanoposdesk.sale', string='Sale', required=True, ondelete='cascade')
    store_id = fields.Many2one(related='sale_id.store_id', store=True)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Product Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', domain="[('tax_type', '=', 'Sales'), ('active', '=', True)]")
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Float(string='Tax', compute='_compute_amount', store=True)
    amount = fields.Float(string='Total', compute='_compute_amount', store=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM')
    uom_qty_multiplier = fields.Float(string='UOM Multiplier', default=1.0)
    available_uom_ids = fields.Many2many('havanoposdesk.uom', compute='_compute_available_uom_ids', store=False)
    cost_price = fields.Float(string='Cost Price', compute='_compute_cost_price', store=True, readonly=False)
    gross_profit = fields.Float(string='Gross Profit', compute='_compute_gross_profit', store=True)

    @api.depends('price_subtotal', 'cost_price', 'accepted_qty', 'sale_id.is_return')
    def _compute_gross_profit(self):
        for line in self:
            sign = -1.0 if line.sale_id.is_return else 1.0
            total_cost = line.cost_price * line.accepted_qty * sign
            line.gross_profit = line.price_subtotal - total_cost

    @api.depends('product_id', 'rate')
    def _compute_cost_price(self):
        for line in self:
            if not line.product_id:
                line.cost_price = 0.0
                continue
            
            # If user manually changed the rate (selling price)
            if line.rate != line.product_id.selling_price:
                # Use Average cost from costing table
                avg_cost_rec = self.env['havanoposdesk.product.costing'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('cost_type', '=', 'average')
                ], order='id desc', limit=1)
                line.cost_price = avg_cost_rec.price if avg_cost_rec else (line.product_id.buying_price or line.product_id.cost_price or 0.0)
            else:
                # Use normal cost (product's buying_price or cost_price)
                line.cost_price = line.product_id.buying_price or line.product_id.cost_price or 0.0

    @api.depends('accepted_qty', 'rate', 'tax_ids', 'sale_id.is_return')
    def _compute_amount(self):
        for record in self:
            sign = -1.0 if record.sale_id.is_return else 1.0
            base_amount = record.accepted_qty * record.rate
            taxes = record.tax_ids
            
            inclusive_taxes = taxes.filtered(lambda t: t.is_inclusive)
            exclusive_taxes = taxes.filtered(lambda t: not t.is_inclusive)
            
            rate_incl = sum(inclusive_taxes.mapped('rate')) / 100.0
            rate_excl = sum(exclusive_taxes.mapped('rate')) / 100.0
            
            untaxed_amount = base_amount / (1.0 + rate_incl)
            inclusive_tax_amount = base_amount - untaxed_amount
            exclusive_tax_amount = untaxed_amount * rate_excl
            
            record.price_subtotal = untaxed_amount * sign
            record.price_tax = (inclusive_tax_amount + exclusive_tax_amount) * sign
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
                ('pricelist_id.type', '=', 'selling')
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
                
            line.tax_ids = [(6, 0, line.product_id.sale_tax_ids.ids)]
            
            if line.uom_id == line.product_id.uom_id:
                line.rate = line.product_id.selling_price
                line.cost_price = line.product_id.buying_price or line.product_id.cost_price or 0.0
                line.uom_qty_multiplier = 1.0
            else:
                price_record = self.env['havanoposdesk.product.uom.price'].search([
                    ('product_id', '=', line.product_id.id),
                    ('uom_id', '=', line.uom_id.id),
                    ('pricelist_id.type', '=', 'selling')
                ], limit=1)
                if price_record:
                    line.rate = price_record.price
                    line.uom_qty_multiplier = price_record.qty_to_be_sold
                    base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                    line.cost_price = base_cost * price_record.qty_to_be_sold
                else:
                    line.rate = line.product_id.selling_price
                    line.uom_qty_multiplier = 1.0

    @api.onchange('rate')
    def _onchange_rate(self):
        if self.tenant_id.restrict_price_modification and not self.env.user.has_group('havanoposdesk_odoo.group_tenant_admin'):
            self.rate = self._origin.rate if getattr(self, '_origin', False) else (self.product_id.selling_price if self.product_id else 0.0)
            return {
                'warning': {
                    'title': 'Price Modification Restricted',
                    'message': 'You cannot edit prices. Please contact the admin if you wish to change the price.'
                }
            }

        if self.product_id:
            if self.rate != self.product_id.selling_price:
                avg_cost_rec = self.env['havanoposdesk.product.costing'].sudo().search([
                    ('product_id', '=', self.product_id.id),
                    ('cost_type', '=', 'average')
                ], order='id desc', limit=1)
                self.cost_price = avg_cost_rec.price if avg_cost_rec else (self.product_id.buying_price or self.product_id.cost_price or 0.0)
            else:
                self.cost_price = self.product_id.buying_price or self.product_id.cost_price or 0.0

    @api.onchange('accepted_qty', 'product_id')
    def _onchange_qty(self):
        allow_negative = self.env.user.tenant_id.allow_negative_stock
        if not allow_negative and self.product_id and self.accepted_qty > self.product_id.opening_stock:
            return {
                'warning': {
                    'title': 'Insufficient Stock',
                    'message': f'You only have {self.product_id.opening_stock} of {self.product_id.name} on hand.',
                }
            }

    @api.constrains('accepted_qty')
    def _check_stock(self):
        allow_negative = self.env.user.tenant_id.allow_negative_stock
        for line in self:
            if line.accepted_qty < 0:
                continue
            if not allow_negative and line.product_id and line.accepted_qty > line.product_id.opening_stock:
                raise ValidationError(f"You cannot sell {line.accepted_qty} of {line.product_id.name} because you only have {line.product_id.opening_stock} on hand.")
