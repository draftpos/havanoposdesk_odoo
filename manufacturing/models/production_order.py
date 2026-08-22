from odoo import api, fields, models

class HavanoPosDeskProductionOrder(models.Model):
    _name = 'havanoposdesk.production.order'
    _description = 'Production Order'

    name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True, default='New')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id)
    bom_id = fields.Many2one('havanoposdesk.manufacturing.bom', string='Bill of Materials', required=True)
    qty_to_produce = fields.Float(string='Quantity to Produce', default=1.0, required=True)
    
    raw_material_ids = fields.One2many(
        'havanoposdesk.production.order.raw_material', 
        'order_id', 
        string='Raw Materials'
    )
    output_ids = fields.One2many(
        'havanoposdesk.production.order.output', 
        'order_id', 
        string='Outputs'
    )
    raw_material_product_ids = fields.Many2many(
        'havanoposdesk.product',
        compute='_compute_raw_material_product_ids'
    )
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)

    state = fields.Selection([
        ('draft', 'Draft'),
        ('completed', 'Completed')
    ], string='Status', default='draft', required=True, copy=False)

    @api.depends('raw_material_ids.total_price')
    def _compute_total_cost(self):
        for order in self:
            order.total_cost = sum(order.raw_material_ids.mapped('total_price'))

    @api.depends('raw_material_ids.product_id')
    def _compute_raw_material_product_ids(self):
        for order in self:
            order.raw_material_product_ids = order.raw_material_ids.mapped('product_id').ids

    @api.onchange('bom_id', 'qty_to_produce')
    def _onchange_bom_id(self):
        if not self.bom_id:
            self.raw_material_ids = [(5, 0, 0)]
            self.output_ids = [(5, 0, 0)]
            return

        raw_materials = []
        for line in self.bom_id.raw_material_ids:
            if line.product_id:
                raw_materials.append((0, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.qty,
                    'total_qty': line.qty * self.qty_to_produce,
                    'price_unit': line.price_unit,
                }))
        self.raw_material_ids = [(5, 0, 0)] + raw_materials

        outputs = []
        for line in self.bom_id.output_ids:
            if line.product_id:
                outputs.append((0, 0, {
                    'product_id': line.product_id.id,
                    'qty': line.qty,
                    'total_qty': line.qty * self.qty_to_produce,
                    'price_unit': line.price_unit,
                }))
        self.output_ids = [(5, 0, 0)] + outputs

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.production.order') or 'New'
        return super().create(vals_list)

    def action_complete(self):
        for order in self:
            if order.state == 'completed':
                continue
            
            # Check raw materials deficit
            for raw in order.raw_material_ids:
                if raw.total_qty > raw.on_hand_qty:
                    # Put a warning for deficit
                    raise models.ValidationError(
                        f"Insufficient quantity on hand for raw material: {raw.product_id.name}. Expected: {raw.total_qty}, Available: {raw.on_hand_qty}"
                    )
            
            ledger_obj = self.env['havanoposdesk.stock.ledger'].sudo()
            
            # Deduct raw materials
            for raw in order.raw_material_ids:
                ledger_obj.create({
                    'product_id': raw.product_id.id,
                    'out_qty': raw.total_qty,
                    'in_qty': 0.0,
                    'type': 'Production (Raw Material)',
                    'doc_no': order.name,
                    'tenant_id': order.tenant_id.id,
                    'buying_price': raw.price_unit,
                })
                
            # Add outputs
            for out in order.output_ids:
                ledger_obj.create({
                    'product_id': out.product_id.id,
                    'in_qty': out.total_qty,
                    'out_qty': 0.0,
                    'type': 'Production (Output)',
                    'doc_no': order.name,
                    'tenant_id': order.tenant_id.id,
                    'buying_price': out.price_unit,
                })
            
            order.state = 'completed'

class HavanoPosDeskProductionOrderRawMaterial(models.Model):
    _name = 'havanoposdesk.production.order.raw_material'
    _description = 'Production Order Raw Material'

    order_id = fields.Many2one('havanoposdesk.production.order', string='Order', ondelete='cascade', required=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Unit Quantity')
    total_qty = fields.Float(string='Total Quantity', required=True)
    price_unit = fields.Float(string='Unit Cost', related='product_id.buying_price', readonly=True)
    total_price = fields.Float(string='Total Cost', compute='_compute_total_price', store=True)
    on_hand_qty = fields.Float(string='Qty On Hand', related='product_id.on_hand_qty', readonly=True)

    @api.depends('total_qty', 'price_unit')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.total_qty * line.price_unit

class HavanoPosDeskProductionOrderOutput(models.Model):
    _name = 'havanoposdesk.production.order.output'
    _description = 'Production Order Output'

    order_id = fields.Many2one('havanoposdesk.production.order', string='Order', ondelete='cascade', required=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Unit Quantity')
    total_qty = fields.Float(string='Total Quantity', required=True)
    price_unit = fields.Float(string='Unit Cost', compute='_compute_output_price', store=True, readonly=False)
    total_price = fields.Float(string='Total Cost', compute='_compute_total_price', store=True)

    @api.depends('order_id.raw_material_ids.total_price', 'order_id.output_ids.total_qty')
    def _compute_output_price(self):
        for line in self:
            if not line.order_id:
                continue
            total_raw_cost = sum(line.order_id.raw_material_ids.mapped('total_price'))
            total_output_qty = sum(line.order_id.output_ids.mapped('total_qty'))
            if total_output_qty > 0:
                line.price_unit = total_raw_cost / total_output_qty
            else:
                line.price_unit = 0.0

    @api.depends('total_qty', 'price_unit')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.total_qty * line.price_unit
