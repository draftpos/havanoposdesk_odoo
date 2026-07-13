from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

class StockEntry(models.Model):
    _name = 'havanoposdesk.stock.entry'
    _description = 'Stock Entry / Material Transfer'
    _order = 'posting_date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    stock_entry_type = fields.Char(string='Stock Entry Type', default='Material Transfer')
    posting_date = fields.Datetime(string='Posting Date', default=fields.Datetime.now)
    from_warehouse = fields.Char(string='Source Warehouse')
    to_warehouse = fields.Char(string='Target Warehouse')
    remarks = fields.Text(string='Remarks')
    docstatus = fields.Integer(string='Docstatus', default=0) # 0 = Draft, 1 = Submitted, 2 = Cancelled
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')
    
    total_outgoing_value = fields.Float(
        string='Total Outgoing Value',
        compute='_compute_totals',
        store=True
    )

    line_ids = fields.One2many('havanoposdesk.stock.entry.line', 'stock_entry_id', string='Items')

    @api.depends('line_ids.basic_amount')
    def _compute_totals(self):
        for record in self:
            record.total_outgoing_value = sum(record.line_ids.mapped('basic_amount'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))

            if vals.get('name', 'New') == 'New':
                seq = self.env['ir.sequence'].next_by_code('havanoposdesk.stock.entry')
                if not seq:
                    count = self.env['havanoposdesk.stock.entry'].sudo().search_count([]) + 1
                    seq = f"STE-{count:05d}"
                vals['name'] = seq
        return super().create(vals_list)

    def write(self, vals):
        for record in self:
            if record.state != 'draft' and any(f not in ['state', 'docstatus'] for f in vals.keys()):
                raise ValidationError("You cannot modify a submitted or cancelled stock entry. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a submitted or cancelled stock entry.")
        return super().unlink()

    def action_submit(self):
        for entry in self:
            if entry.state != 'draft':
                continue
            for line in entry.line_ids:
                # 1. Source warehouse deduction
                if entry.from_warehouse:
                    val_src = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', entry.from_warehouse)
                    ], limit=1)
                    if val_src:
                        val_src.write({'on_hand_qty': val_src.on_hand_qty - line.qty})
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': entry.from_warehouse,
                            'on_hand_qty': -line.qty,
                        })

                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': 0.0,
                        'out_qty': line.qty,
                        'balance_qty': line.product_id.opening_stock - line.qty if not entry.to_warehouse else line.product_id.opening_stock,
                        'store': entry.from_warehouse,
                        'type': 'Stock Entry Transfer Out',
                        'doc_no': entry.name,
                    })

                # 2. Target warehouse addition
                if entry.to_warehouse:
                    val_tgt = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', entry.to_warehouse)
                    ], limit=1)
                    if val_tgt:
                        val_tgt.write({'on_hand_qty': val_tgt.on_hand_qty + line.qty})
                    else:
                        self.env['havanoposdesk.stock.valuation'].sudo().create({
                            'product_id': line.product_id.id,
                            'store': entry.to_warehouse,
                            'on_hand_qty': line.qty,
                        })

                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': line.qty,
                        'out_qty': 0.0,
                        'balance_qty': line.product_id.opening_stock if not entry.from_warehouse else line.product_id.opening_stock,
                        'store': entry.to_warehouse,
                        'type': 'Stock Entry Transfer In',
                        'doc_no': entry.name,
                    })

                # 3. Overall product opening_stock update
                if entry.from_warehouse and not entry.to_warehouse:
                    line.product_id.sudo().opening_stock -= line.qty
                elif entry.to_warehouse and not entry.from_warehouse:
                    line.product_id.sudo().opening_stock += line.qty

            entry.write({'state': 'submitted', 'docstatus': 1})

    def action_cancel(self):
        for entry in self:
            if entry.state != 'submitted':
                continue
            for line in entry.line_ids:
                # Revert source
                if entry.from_warehouse:
                    val_src = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', entry.from_warehouse)
                    ], limit=1)
                    if val_src:
                        val_src.write({'on_hand_qty': val_src.on_hand_qty + line.qty})
                    
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': line.qty,
                        'out_qty': 0.0,
                        'balance_qty': line.product_id.opening_stock + line.qty if not entry.to_warehouse else line.product_id.opening_stock,
                        'store': entry.from_warehouse,
                        'type': 'Transfer Cancelled In',
                        'doc_no': entry.name,
                    })

                # Revert target
                if entry.to_warehouse:
                    val_tgt = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('store', '=', entry.to_warehouse)
                    ], limit=1)
                    if val_tgt:
                        val_tgt.write({'on_hand_qty': val_tgt.on_hand_qty - line.qty})
                    
                    self.env['havanoposdesk.stock.ledger'].sudo().create({
                        'product_id': line.product_id.id,
                        'in_qty': 0.0,
                        'out_qty': line.qty,
                        'balance_qty': line.product_id.opening_stock if not entry.from_warehouse else line.product_id.opening_stock,
                        'store': entry.to_warehouse,
                        'type': 'Transfer Cancelled Out',
                        'doc_no': entry.name,
                    })

                # Revert overall opening stock
                if entry.from_warehouse and not entry.to_warehouse:
                    line.product_id.sudo().opening_stock += line.qty
                elif entry.to_warehouse and not entry.from_warehouse:
                    line.product_id.sudo().opening_stock -= line.qty

            entry.write({'state': 'cancelled', 'docstatus': 2})


class StockEntryLine(models.Model):
    _name = 'havanoposdesk.stock.entry.line'
    _description = 'Stock Entry Line'

    stock_entry_id = fields.Many2one('havanoposdesk.stock.entry', string='Stock Entry', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Item Code', readonly=True)
    qty = fields.Float(string='Quantity', default=1.0)
    uom = fields.Char(string='UOM')
    basic_rate = fields.Float(string='Basic Rate')
    basic_amount = fields.Float(string='Basic Amount', compute='_compute_amount', store=True)

    @api.depends('qty', 'basic_rate')
    def _compute_amount(self):
        for record in self:
            record.basic_amount = record.qty * record.basic_rate

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            self.basic_rate = self.product_id.buying_price or self.product_id.cost_price or 0.0
            self.uom = self.product_id.uom_id.name if self.product_id.uom_id else ''
