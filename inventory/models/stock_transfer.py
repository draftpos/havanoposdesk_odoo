from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime

class StockTransfer(models.Model):
    _name = 'havanoposdesk.stock.transfer'
    _description = 'Stock Transfer'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        required=True,
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    date = fields.Datetime(string='Date', default=fields.Datetime.now, required=True)
    from_store_id = fields.Many2one('havanoposdesk.store', string='From Store', required=True, domain="[('tenant_id', '=', tenant_id)]")
    to_store_id = fields.Many2one('havanoposdesk.store', string='To Store', required=True, domain="[('tenant_id', '=', tenant_id)]")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Transferred')
    ], string='Status', default='draft', readonly=True, copy=False)

    line_ids = fields.One2many('havanoposdesk.stock.transfer.line', 'transfer_id', string='Transfer Lines')

    @api.constrains('from_store_id', 'to_store_id')
    def _check_stores(self):
        for record in self:
            if record.from_store_id == record.to_store_id:
                raise ValidationError("The Source and Destination stores cannot be the same!")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['name'] = tenant._get_next_sequence('trn')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.stock.transfer') or 'New'
        return super().create(vals_list)

    def action_validate(self):
        for record in self:
            if record.state != 'draft':
                continue

            if not record.line_ids:
                raise ValidationError("You cannot validate an empty transfer.")

            for line in record.line_ids:
                if line.qty <= 0:
                    raise ValidationError(f"Quantity for product '{line.product_id.name}' must be greater than zero.")

                # Always check current stock in from_store
                valuation_from = self.env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('store', '=', record.from_store_id.name)
                ], limit=1)
                current_qty = valuation_from.on_hand_qty if valuation_from else 0.0

                # Block if zero stock
                if current_qty <= 0:
                    raise ValidationError(
                        f"Cannot transfer '{line.product_id.name}' from '{record.from_store_id.name}' — "
                        f"there is no stock available (On Hand: {current_qty})."
                    )

                # Block if insufficient stock (when negative stock not allowed)
                allow_negative = record.tenant_id.allow_negative_stock
                if not allow_negative and current_qty < line.qty:
                    raise ValidationError(
                        f"Insufficient stock for '{line.product_id.name}' in '{record.from_store_id.name}'. "
                        f"Available: {current_qty}, Requested: {line.qty}"
                    )

                # Deduct from source store
                if valuation_from:
                    valuation_from.write({'on_hand_qty': valuation_from.on_hand_qty - line.qty})
                else:
                    self.env['havanoposdesk.stock.valuation'].sudo().create({
                        'product_id': line.product_id.id,
                        'store': record.from_store_id.name,
                        'on_hand_qty': -line.qty,
                        'tenant_id': record.tenant_id.id,
                    })

                self.env['havanoposdesk.stock.ledger'].sudo().create({
                    'product_id': line.product_id.id,
                    'in_qty': 0.0,
                    'out_qty': line.qty,
                    'balance_qty': (valuation_from.on_hand_qty - line.qty) if valuation_from else -line.qty,
                    'buying_price': line.product_id.buying_price or 0.0,
                    'store': record.from_store_id.name,
                    'type': 'Transfer Out',
                    'doc_no': record.name,
                    'tenant_id': record.tenant_id.id,
                })

                # Add to destination store
                valuation_to = self.env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('store', '=', record.to_store_id.name)
                ], limit=1)
                if valuation_to:
                    valuation_to.write({'on_hand_qty': valuation_to.on_hand_qty + line.qty})
                else:
                    self.env['havanoposdesk.stock.valuation'].sudo().create({
                        'product_id': line.product_id.id,
                        'store': record.to_store_id.name,
                        'on_hand_qty': line.qty,
                        'tenant_id': record.tenant_id.id,
                    })

                self.env['havanoposdesk.stock.ledger'].sudo().create({
                    'product_id': line.product_id.id,
                    'in_qty': line.qty,
                    'out_qty': 0.0,
                    'balance_qty': (valuation_to.on_hand_qty + line.qty) if valuation_to else line.qty,
                    'buying_price': line.product_id.buying_price or 0.0,
                    'store': record.to_store_id.name,
                    'type': 'Transfer In',
                    'doc_no': record.name,
                    'tenant_id': record.tenant_id.id,
                })

            record.write({'state': 'done'})


class StockTransferLine(models.Model):
    _name = 'havanoposdesk.stock.transfer.line'
    _description = 'Stock Transfer Line'

    transfer_id = fields.Many2one('havanoposdesk.stock.transfer', string='Transfer', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(related='transfer_id.tenant_id', store=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True, domain="[('tenant_id', '=', tenant_id)]")
    uom_id = fields.Many2one('havanoposdesk.uom', string='Unit of Measure')
    available_uom_ids = fields.Many2many('havanoposdesk.uom', compute='_compute_available_uom_ids', store=False)
    qty = fields.Float(string='Quantity', default=1.0, required=True)

    @api.depends('product_id')
    def _compute_available_uom_ids(self):
        for line in self:
            if not line.product_id:
                line.available_uom_ids = False
                continue
            uom_ids = line.product_id.uom_id.ids if line.product_id.uom_id else []
            # Include UOMs from advanced pricing (selling prices)
            prices = self.env['havanoposdesk.product.uom.price'].search([
                ('product_id', '=', line.product_id.id),
            ])
            uom_ids.extend(prices.mapped('uom_id.id'))
            line.available_uom_ids = [(6, 0, list(set(uom_ids)))]

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                line.uom_id = False
                continue
            if not line.uom_id or line.uom_id.id not in line.available_uom_ids.ids:
                line.uom_id = line.product_id.uom_id
