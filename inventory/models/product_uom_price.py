from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HavanoposdeskProductUomPrice(models.Model):
    _name = 'havanoposdesk.product.uom.price'
    _description = 'Product UOM Price'

    def _auto_init(self):
        res = super()._auto_init()
        cr = self.env.cr
        try:
            with cr.savepoint():
                cr.execute("ALTER TABLE havanoposdesk_product_uom_price ADD COLUMN IF NOT EXISTS initial_stock DOUBLE PRECISION DEFAULT 0.0;")
        except Exception:
            pass
        return res

    _sql_constraints = [
        ('product_store_pricelist_uom_uniq', 
         'unique (product_id, store_id, pricelist_id, uom_id)', 
         'A price line for this combination of Store, Pricelist, and Unit of Measure already exists for this product! At least one must be different.')
    ]

    product_id = fields.Many2one('havanoposdesk.product', string='Product', required=True, ondelete='cascade')
    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True)
    pricelist_id = fields.Many2one('havanoposdesk.pricelist', string='Pricelist', required=True)
    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM', required=True)
    qty_to_be_sold = fields.Float(string='Qty to be Sold', default=1.0, required=True, help="Conversion multiplier (e.g. 1 Box = 24 items, set this to 24)")
    price = fields.Float(string='Price', required=True, default=0.0)
    initial_stock = fields.Float(string='Initial Qty', default=0.0, help="Initial opening stock quantity for this store")
    on_hand_qty = fields.Float(string='Store On Hand', compute='_compute_on_hand_qty')

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        required=True,
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )

    @api.depends('product_id', 'store_id')
    def _compute_on_hand_qty(self):
        for record in self:
            if record.product_id and record.store_id:
                valuation = self.env['havanoposdesk.stock.valuation'].search([
                    ('product_id', '=', record.product_id.id),
                    ('store_id', '=', record.store_id.id)
                ])
                record.on_hand_qty = sum(valuation.mapped('on_hand_qty'))
            else:
                record.on_hand_qty = 0.0

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if rec.initial_stock > 0 and rec.product_id and rec.store_id and not self.env.context.get('from_product_creation'):
                val_count = self.env['havanoposdesk.stock.valuation'].search_count([
                    ('product_id', '=', rec.product_id.id),
                    ('store_id', '=', rec.store_id.id)
                ])
                if val_count == 0:
                    adj = self.env['havanoposdesk.stock.adjustment'].with_context(from_product_creation=True).create({
                        'store_id': rec.store_id.id,
                        'fetch_all_data': False,
                        'tenant_id': rec.tenant_id.id,
                        'line_ids': [(0, 0, {
                            'product_id': rec.product_id.id,
                            'on_hand': rec.initial_stock,
                            'counted': rec.initial_stock,
                        })]
                    })
                    adj.action_post()
        return records

    @api.depends('product_id', 'store_id', 'pricelist_id', 'uom_id', 'price')
    def _compute_display_name(self):
        for record in self:
            prod_name = record.product_id.name if record.product_id else ''
            store_name = record.store_id.name if record.store_id else ''
            pl_name = record.pricelist_id.name if record.pricelist_id else ''
            uom_name = record.uom_id.name if record.uom_id else ''
            record.display_name = f"{prod_name} | {store_name} | {pl_name} ({uom_name}): {record.price}"

    @api.constrains('product_id', 'store_id', 'pricelist_id', 'uom_id')
    def _check_unique_store_pricelist_uom(self):
        for record in self:
            if record.product_id and record.store_id and record.pricelist_id and record.uom_id:
                domain = [
                    ('product_id', '=', record.product_id.id),
                    ('store_id', '=', record.store_id.id),
                    ('pricelist_id', '=', record.pricelist_id.id),
                    ('uom_id', '=', record.uom_id.id),
                    ('id', '!=', record.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_(
                        "You cannot save more than one line with the same Store (%s), Pricelist (%s), and Unit of Measure (%s) for product '%s'. At least one of Store, Pricelist, or UoM must be different."
                    ) % (record.store_id.name, record.pricelist_id.name, record.uom_id.name, record.product_id.name))

