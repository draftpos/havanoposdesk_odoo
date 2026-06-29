from odoo import models, fields, tools

class CategorySalesReport(models.Model):
    _name = 'havanoposdesk.category.sales.report'
    _description = 'Category Sales Report'
    _auto = False

    category_id = fields.Many2one('havanoposdesk.category', string='Category', readonly=True)
    qty = fields.Float(string='Qty Sold', readonly=True)
    cost_price = fields.Float(string='Buying Price', readonly=True)
    selling_price = fields.Float(string='Selling Price', readonly=True)
    profit = fields.Float(string='Profit', readonly=True)
    profit_margin = fields.Float(string='Profit Margin (%)', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    MIN(l.id) as id,
                    p.category_id,
                    SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) as qty,
                    CASE 
                        WHEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) > 0 
                        THEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty * p.buying_price ELSE l.accepted_qty * p.buying_price END) / SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END)
                        ELSE 0 
                    END as cost_price,
                    CASE 
                        WHEN SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END) > 0 
                        THEN SUM(CASE WHEN s.is_return THEN -l.amount ELSE l.amount END) / SUM(CASE WHEN s.is_return THEN -l.accepted_qty ELSE l.accepted_qty END)
                        ELSE 0 
                    END as selling_price,
                    SUM(CASE WHEN s.is_return THEN -l.amount ELSE l.amount END) - SUM(CASE WHEN s.is_return THEN -l.accepted_qty * p.buying_price ELSE l.accepted_qty * p.buying_price END) as profit,
                    CASE 
                        WHEN SUM(CASE WHEN s.is_return THEN -l.amount ELSE l.amount END) > 0 
                        THEN ((SUM(CASE WHEN s.is_return THEN -l.amount ELSE l.amount END) - SUM(CASE WHEN s.is_return THEN -l.accepted_qty * p.buying_price ELSE l.accepted_qty * p.buying_price END)) / SUM(CASE WHEN s.is_return THEN -l.amount ELSE l.amount END)) * 100 
                        ELSE 0 
                    END as profit_margin,
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
                    p.category_id, l.tenant_id, s.store_id
            )
        """ % (self._table,))
