from odoo import models, fields, tools

class ItemProfitabilityReport(models.Model):
    _name = 'havanoposdesk.item.profitability.report'
    _description = 'Item Profitability Report'
    _auto = False

    product_id = fields.Many2one('havanoposdesk.product', string='Product', readonly=True)
    item_code = fields.Char(string='Item Code', readonly=True)
    name = fields.Char(string='Item Name', readonly=True)
    category_id = fields.Many2one('havanoposdesk.category', string='Category', readonly=True)
    qty = fields.Float(string='Qty Sold', readonly=True)
    cost_price = fields.Float(string='Buying Price', readonly=True)
    selling_price = fields.Float(string='Selling Price', readonly=True)
    total_sales = fields.Float(string='Total Sales', readonly=True)
    profit = fields.Float(string='Profit', readonly=True)
    profit_margin = fields.Float(string='Profit Margin (%)', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    MIN(l.id) as id,
                    l.product_id,
                    p.category_id,
                    p.item_code,
                    p.name,
                    SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) as qty,
                    CASE 
                        WHEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) > 0 
                        THEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty * l.cost_price ELSE l.accepted_qty * l.cost_price END) / SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END)
                        ELSE 0 
                    END as cost_price,
                    CASE 
                        WHEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) > 0 
                        THEN SUM(l.amount) / SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END)
                        ELSE 0 
                    END as selling_price,
                    SUM(l.amount) as total_sales,
                    SUM(l.amount) - SUM(CASE WHEN s.is_return THEN -l.accepted_qty * l.cost_price ELSE l.accepted_qty * l.cost_price END) as profit,
                    CASE 
                        WHEN SUM(l.amount) > 0 
                        THEN ((SUM(l.amount) - SUM(CASE WHEN s.is_return THEN -l.accepted_qty * l.cost_price ELSE l.accepted_qty * l.cost_price END)) / SUM(l.amount)) * 100 
                        ELSE 0 
                    END as profit_margin,
                    s.posting_date as date,
                    l.tenant_id,
                    s.store_id
                FROM
                    havanoposdesk_sale_line l
                JOIN
                    havanoposdesk_product p ON p.id = l.product_id
                JOIN
                    havanoposdesk_sale s ON s.id = l.sale_id
                WHERE
                    s.state IN ('confirmed', 'done')
                GROUP BY
                    l.product_id, p.category_id, p.item_code, p.name, s.posting_date, l.tenant_id, s.store_id
            )
        """ % (self._table,))


