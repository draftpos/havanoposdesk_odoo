from odoo import api, fields, models

class HavanoPosDeskManufacturingBom(models.Model):
    _name = 'havanoposdesk.manufacturing.bom'
    _description = 'Bill of Materials'

    _constraints = [
        models.Constraint('unique(name, tenant_id)', 'The BOM Reference must be unique per tenant!')
    ]

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
    raw_material_product_ids = fields.Many2many(
        'havanoposdesk.product',
        compute='_compute_raw_material_product_ids'
    )
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    output_summary = fields.Char(string='Outputs Summary', compute='_compute_output_summary')

    @api.depends('raw_material_ids.total_price')
    def _compute_total_cost(self):
        for bom in self:
            bom.total_cost = sum(bom.raw_material_ids.mapped('total_price'))

    @api.depends('output_ids.product_id', 'output_ids.qty')
    def _compute_output_summary(self):
        for bom in self:
            summaries = [f"{line.qty}x {line.product_id.name}" for line in bom.output_ids if line.product_id]
            bom.output_summary = ", ".join(summaries)

    @api.depends('raw_material_ids.product_id')
    def _compute_raw_material_product_ids(self):
        for bom in self:
            bom.raw_material_product_ids = bom.raw_material_ids.mapped('product_id').ids

class HavanoPosDeskManufacturingBomLine(models.Model):
    _name = 'havanoposdesk.manufacturing.bom.line'
    _description = 'BOM Raw Material Line'

    bom_id = fields.Many2one('havanoposdesk.manufacturing.bom', string='BOM', ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'havanoposdesk.product', 
        string='Item', 
        required=True,
        domain="[('not_for_sale', '=', True)]"
    )
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    total_qty = fields.Float(string='Total Quantity', compute='_compute_total_qty', store=True)
    price_unit = fields.Float(string='Unit Cost', related='product_id.buying_price', readonly=True)
    total_price = fields.Float(string='Total Cost', compute='_compute_total_price', store=True)

    @api.depends('qty')
    def _compute_total_qty(self):
        for line in self:
            line.total_qty = line.qty

    @api.depends('qty', 'price_unit')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.qty * line.price_unit

class HavanoPosDeskManufacturingBomOutput(models.Model):
    _name = 'havanoposdesk.manufacturing.bom.output'
    _description = 'BOM Output Line'

    bom_id = fields.Many2one('havanoposdesk.manufacturing.bom', string='BOM', ondelete='cascade', required=True)
    product_id = fields.Many2one(
        'havanoposdesk.product', 
        string='Item', 
        required=True
    )
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', related='product_id.uom_id', readonly=True)
    qty = fields.Float(string='Quantity', default=1.0, required=True)
    total_qty = fields.Float(string='Total Quantity', compute='_compute_total_qty', store=True)
    price_unit = fields.Float(string='Unit Cost', compute='_compute_output_price', store=True, readonly=False)
    total_price = fields.Float(string='Total Cost', compute='_compute_total_price', store=True)

    @api.depends('qty')
    def _compute_total_qty(self):
        for line in self:
            line.total_qty = line.qty

    @api.depends('bom_id.raw_material_ids.total_price', 'bom_id.output_ids.qty')
    def _compute_output_price(self):
        for line in self:
            if not line.bom_id:
                continue
            total_raw_cost = sum(line.bom_id.raw_material_ids.mapped('total_price'))
            total_output_qty = sum(line.bom_id.output_ids.mapped('qty'))
            if total_output_qty > 0:
                line.price_unit = total_raw_cost / total_output_qty
            else:
                line.price_unit = 0.0

    @api.depends('qty', 'price_unit')
    def _compute_total_price(self):
        for line in self:
            line.total_price = line.qty * line.price_unit
