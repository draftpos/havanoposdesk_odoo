from odoo import api, fields, models

class HavanoPosDeskManufacturingBom(models.Model):
    _name = 'havanoposdesk.manufacturing.bom'
    _description = 'Bill of Materials'

    name = fields.Char(string='BOM Reference', required=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id)
    
    raw_material_ids = fields.One2many(
        'havanoposdesk.manufacturing.bom.line', 
        'bom_id', 
        string='Raw Materials'
    )
    output_ids = fields.One2many(
        'havanoposdesk.manufacturing.bom.output', 
        'bom_id', 
        string='Outputs'
    )

class HavanoPosDeskManufacturingBomLine(models.Model):
    _name = 'havanoposdesk.manufacturing.bom.line'
    _description = 'BOM Raw Material Line'

    bom_id = fields.Many2one('havanoposdesk.manufacturing.bom', string='BOM', ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'product.product', 
        string='Item', 
        required=True,
        domain="[('sale_ok', '=', False)]"
    )
    uom_id = fields.Many2one('uom.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    total_qty = fields.Float(string='Total Quantity', compute='_compute_total_qty', store=True)

    @api.depends('qty')
    def _compute_total_qty(self):
        for line in self:
            line.total_qty = line.qty

class HavanoPosDeskManufacturingBomOutput(models.Model):
    _name = 'havanoposdesk.manufacturing.bom.output'
    _description = 'BOM Output Line'

    bom_id = fields.Many2one('havanoposdesk.manufacturing.bom', string='BOM', ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'product.product', 
        string='Item', 
        required=True
    )
    uom_id = fields.Many2one('uom.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    total_qty = fields.Float(string='Total Quantity', compute='_compute_total_qty', store=True)

    @api.depends('qty')
    def _compute_total_qty(self):
        for line in self:
            line.total_qty = line.qty
