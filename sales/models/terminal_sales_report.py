from odoo import models, fields, tools

class TerminalSalesReport(models.Model):
    _name = 'havanoposdesk.terminal.sales.report'
    _description = 'Terminal Sales Report'
    _auto = False

    terminal_id = fields.Many2one('havanoposdesk.pos.terminal', string='POS Terminal', readonly=True)
    salesperson_id = fields.Many2one('res.users', string='Cashier', readonly=True)
    qty = fields.Float(string='Qty Sold', readonly=True)
    cost_price = fields.Float(string='Cost Price', readonly=True)
    selling_price = fields.Float(string='Selling Price', readonly=True)
    total_sales = fields.Monetary(string='Total Sales', readonly=True, currency_field='currency_id')
    profit = fields.Monetary(string='Profit', readonly=True, currency_field='currency_id')
    profit_margin = fields.Float(string='Profit Margin (%)', readonly=True)
    date = fields.Date(string='Date', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)
    create_date = fields.Datetime(string='Created On', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    MIN(l.id) as id,
                    s.terminal_id,
                    s.salesperson_id,
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
                        THEN ((SUM(l.amount) - SUM(CASE WHEN s.is_return THEN -l.accepted_qty * l.cost_price ELSE l.accepted_qty * l.cost_price END)) / SUM(l.amount))
                        ELSE 0 
                    END as profit_margin,
                    s.posting_date as date,
                    s.create_uid as create_uid,
                    s.create_date as create_date,
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
                    s.terminal_id, s.salesperson_id, s.posting_date, s.create_uid, s.create_date, l.tenant_id, s.store_id
            )
        """ % (self._table,))

