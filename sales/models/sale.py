from odoo import models, fields, api
from datetime import datetime, time
from odoo.exceptions import ValidationError

class Sale(models.Model):
    _name = 'havanoposdesk.sale'
    _description = 'Sale'
    _order = 'date desc, id desc'

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
    date = fields.Datetime(string='Sale Date', default=fields.Datetime.now, required=True)
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amount_total', store=True)
    amount_tax = fields.Float(string='Taxes', compute='_compute_amount_total', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user.id)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done')
    ], string='Status', default='done', required=True)

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
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale') or 'New'
            
            # Sync store and store_id
            if 'store' in vals and not vals.get('store_id'):
                store = self.env['havanoposdesk.store'].search([('name', '=', vals['store'])], limit=1)
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

    def write(self, vals):
        # Sync values on write
        if 'store' in vals and 'store_id' not in vals:
            store = self.env['havanoposdesk.store'].search([('name', '=', vals['store'])], limit=1)
            if store:
                vals['store_id'] = store.id
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
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Item Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', domain="[('tax_type', '=', 'Sales'), ('active', '=', True)]")
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
            self.rate = self.product_id.selling_price
            self.tax_ids = [(6, 0, self.product_id.sale_tax_ids.ids)]

    @api.onchange('accepted_qty', 'product_id')
    def _onchange_qty(self):
        allow_negative = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.allow_negative_stock', 'True') == 'True'
        if not allow_negative and self.product_id and self.accepted_qty > self.product_id.opening_stock:
            return {
                'warning': {
                    'title': 'Insufficient Stock',
                    'message': f'You only have {self.product_id.opening_stock} of {self.product_id.name} on hand.',
                }
            }

    @api.constrains('accepted_qty')
    def _check_stock(self):
        allow_negative = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.allow_negative_stock', 'True') == 'True'
        for line in self:
            if line.accepted_qty < 0:
                raise ValidationError("Quantity cannot be negative.")
            if not allow_negative and line.product_id and line.accepted_qty > line.product_id.opening_stock:
                raise ValidationError(f"You cannot sell {line.accepted_qty} of {line.product_id.name} because you only have {line.product_id.opening_stock} on hand.")