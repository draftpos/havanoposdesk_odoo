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

    @api.onchange('bom_id', 'qty_to_produce')
    def _onchange_bom_id(self):
        if not self.bom_id:
            self.raw_material_ids = [(5, 0, 0)]
            self.output_ids = [(5, 0, 0)]
            return

        raw_materials = []
        for line in self.bom_id.raw_material_ids:
            raw_materials.append((0, 0, {
                'product_id': line.product_id.id,
                'qty': line.qty,
                'total_qty': line.qty * self.qty_to_produce,
            }))
        self.raw_material_ids = [(5, 0, 0)] + raw_materials

        outputs = []
        for line in self.bom_id.output_ids:
            outputs.append((0, 0, {
                'product_id': line.product_id.id,
                'qty': line.qty,
                'total_qty': line.qty * self.qty_to_produce,
            }))
        self.output_ids = [(5, 0, 0)] + outputs

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.production.order') or 'New'
        return super().create(vals_list)

class HavanoPosDeskProductionOrderRawMaterial(models.Model):
    _name = 'havanoposdesk.production.order.raw_material'
    _description = 'Production Order Raw Material'

    order_id = fields.Many2one('havanoposdesk.production.order', string='Order', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='Item', required=True)
    uom_id = fields.Many2one('uom.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Unit Quantity')
    total_qty = fields.Float(string='Total Quantity', required=True)

class HavanoPosDeskProductionOrderOutput(models.Model):
    _name = 'havanoposdesk.production.order.output'
    _description = 'Production Order Output'

    order_id = fields.Many2one('havanoposdesk.production.order', string='Order', ondelete='cascade', required=True)
    product_id = fields.Many2one('product.product', string='Item', required=True)
    uom_id = fields.Many2one('uom.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Unit Quantity')
    total_qty = fields.Float(string='Total Quantity', required=True)
