from odoo import models, fields, tools

class SalesStockValuationReport(models.Model):
    _name = 'havanoposdesk.sales.stock.valuation.report'
    _description = 'Sales &stock Valuation'
    _auto = False
    _order = 'store_name asc, pricelist_name asc'

    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)
    store_name = fields.Char(string='Store Name', readonly=True)
    pricelist_id = fields.Many2one('havanoposdesk.pricelist', string='Pricelist', readonly=True)
    pricelist_name = fields.Char(string='Pricelist Name', readonly=True)
    closing_stock = fields.Float(string='Closing Stock', readonly=True)
    valuation_amount = fields.Monetary(string='Stock Valuation', currency_field='currency_id', readonly=True)
    sales_amount = fields.Monetary(string='Actual Sales', currency_field='currency_id', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    (s.id * 100000 + pl.id) as id,
                    s.id as store_id,
                    s.name as store_name,
                    pl.id as pricelist_id,
                    pl.name as pricelist_name,
                    COALESCE(stock_sub.closing_stock, 0.0) as closing_stock,
                    COALESCE(val_sub.valuation_amount, 0.0) as valuation_amount,
                    COALESCE(sales_sub.sales_amount, 0.0) as sales_amount,
                    s.tenant_id as tenant_id,
                    COALESCE(s.currency_id, t.currency_id) as currency_id
                FROM havanoposdesk_store s
                JOIN havanoposdesk_tenant t ON t.id = s.tenant_id
                JOIN havanoposdesk_pricelist pl ON pl.tenant_id = s.tenant_id AND pl.type = 'selling'
                LEFT JOIN (
                    SELECT store_id, SUM(on_hand_qty) as closing_stock
                    FROM havanoposdesk_stock_valuation
                    GROUP BY store_id
                ) stock_sub ON stock_sub.store_id = s.id
                LEFT JOIN (
                    SELECT 
                        sv.store_id,
                        pl2.id as pricelist_id,
                        SUM(sv.on_hand_qty * COALESCE(pup.price, p.selling_price, 0.0)) as valuation_amount
                    FROM havanoposdesk_stock_valuation sv
                    JOIN havanoposdesk_product p ON p.id = sv.product_id
                    JOIN havanoposdesk_pricelist pl2 ON pl2.tenant_id = sv.tenant_id AND pl2.type = 'selling'
                    LEFT JOIN havanoposdesk_product_uom_price pup 
                        ON pup.product_id = sv.product_id 
                        AND pup.store_id = sv.store_id 
                        AND pup.pricelist_id = pl2.id
                        AND (pup.uom_id = p.uom_id OR pup.uom_id IS NULL)
                    GROUP BY sv.store_id, pl2.id
                ) val_sub ON val_sub.store_id = s.id AND val_sub.pricelist_id = pl.id
                LEFT JOIN (
                    SELECT 
                        s_inner.store_id, 
                        COALESCE(s_inner.pricelist_id, st_inner.pricelist_id) as pricelist_id, 
                        SUM(s_inner.amount_total_base) as sales_amount
                    FROM havanoposdesk_sale s_inner
                    JOIN havanoposdesk_store st_inner ON st_inner.id = s_inner.store_id
                    WHERE s_inner.state IN ('confirmed', 'done')
                    GROUP BY s_inner.store_id, COALESCE(s_inner.pricelist_id, st_inner.pricelist_id)
                ) sales_sub ON sales_sub.store_id = s.id AND sales_sub.pricelist_id = pl.id
            )
        """ % (self._table,))
