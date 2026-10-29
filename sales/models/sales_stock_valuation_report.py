from odoo import models, fields, tools

class SalesStockValuationReport(models.Model):
    _name = 'havanoposdesk.sales.stock.valuation.report'
    _description = 'Sales &stock Valuation'
    _auto = False
    _order = 'store_name asc'

    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)
    store_name = fields.Char(string='Store Name', readonly=True)
    closing_stock = fields.Float(string='Closing Stock', readonly=True)
    wholesale_qty = fields.Float(string='Wholesale', readonly=True)
    retail_qty = fields.Float(string='Retail', readonly=True)
    total_qty = fields.Float(string='Total', readonly=True)
    sales_amount = fields.Monetary(string='Actual Sales', currency_field='currency_id', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)

    # Backward compatibility aliases
    wholesale_valuation = fields.Float(string='Wholesale', readonly=True)
    retail_valuation = fields.Float(string='Retail', readonly=True)
    total_valuation = fields.Float(string='Total', readonly=True)
    other_valuation = fields.Float(string='Other Pricelists', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT 
                    s.id as id,
                    s.id as store_id,
                    s.name as store_name,
                    COALESCE(stock_sub.closing_stock, 0.0) as closing_stock,
                    COALESCE(sales_qty_sub.wholesale_qty, 0.0) as wholesale_qty,
                    COALESCE(sales_qty_sub.retail_qty, 0.0) as retail_qty,
                    (COALESCE(sales_qty_sub.wholesale_qty, 0.0) + COALESCE(sales_qty_sub.retail_qty, 0.0)) as total_qty,
                    COALESCE(sales_qty_sub.wholesale_qty, 0.0) as wholesale_valuation,
                    COALESCE(sales_qty_sub.retail_qty, 0.0) as retail_valuation,
                    (COALESCE(sales_qty_sub.wholesale_qty, 0.0) + COALESCE(sales_qty_sub.retail_qty, 0.0)) as total_valuation,
                    0.0 as other_valuation,
                    COALESCE(sales_sub.total_sales, 0.0) as sales_amount,
                    s.tenant_id as tenant_id,
                    COALESCE(s.currency_id, t.currency_id) as currency_id
                FROM havanoposdesk_store s
                JOIN havanoposdesk_tenant t ON t.id = s.tenant_id
                LEFT JOIN (
                    SELECT store_id, SUM(on_hand_qty) as closing_stock
                    FROM havanoposdesk_stock_valuation
                    GROUP BY store_id
                ) stock_sub ON stock_sub.store_id = s.id
                LEFT JOIN (
                    SELECT 
                        s_inner.store_id,
                        SUM(CASE 
                            WHEN pl.name ILIKE '%%wholesale%%' 
                            THEN (CASE WHEN s_inner.is_return THEN -COALESCE(sl.accepted_qty, 0.0) ELSE COALESCE(sl.accepted_qty, 0.0) END) 
                            ELSE 0.0 
                        END) as wholesale_qty,
                        SUM(CASE 
                            WHEN pl.name ILIKE '%%retail%%' 
                            THEN (CASE WHEN s_inner.is_return THEN -COALESCE(sl.accepted_qty, 0.0) ELSE COALESCE(sl.accepted_qty, 0.0) END) 
                            ELSE 0.0 
                        END) as retail_qty
                    FROM havanoposdesk_sale s_inner
                    JOIN havanoposdesk_sale_line sl ON sl.sale_id = s_inner.id 
                        AND (sl.display_type IS NULL OR sl.display_type NOT IN ('line_section', 'line_note'))
                    LEFT JOIN havanoposdesk_store st_inner ON st_inner.id = s_inner.store_id
                    LEFT JOIN havanoposdesk_pricelist pl ON pl.id = COALESCE(s_inner.pricelist_id, st_inner.pricelist_id)
                    WHERE s_inner.state IN ('confirmed', 'done')
                    GROUP BY s_inner.store_id
                ) sales_qty_sub ON sales_qty_sub.store_id = s.id
                LEFT JOIN (
                    SELECT 
                        s_inner.store_id, 
                        SUM(s_inner.amount_total_base) as total_sales
                    FROM havanoposdesk_sale s_inner
                    WHERE s_inner.state IN ('confirmed', 'done')
                    GROUP BY s_inner.store_id
                ) sales_sub ON sales_sub.store_id = s.id
            )
        """ % (self._table,))
