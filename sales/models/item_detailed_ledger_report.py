from odoo import models, fields, tools, api

class ItemDetailedLedgerReport(models.Model):
    _name = 'havanoposdesk.item.detailed.ledger.report'
    _description = 'Item Detailed Ledger Report'
    _auto = False

    product_id = fields.Many2one('havanoposdesk.product', string='Item', readonly=True)
    item_code = fields.Char(string='Item Code', readonly=True)
    item_name = fields.Char(string='Item Name', readonly=True)
    category_id = fields.Many2one('havanoposdesk.category', string='Item Group', readonly=True)
    opening_stock = fields.Float(string='Opening Stock', readonly=True)
    purchases = fields.Float(string='Purchases', readonly=True)
    transfers = fields.Float(string='Transfers', readonly=True)
    qty_sold = fields.Float(string='Qty Sold', readonly=True)
    closing_stock = fields.Float(string='Closing Stock', readonly=True)
    pricelist_id = fields.Many2one('havanoposdesk.pricelist', string='Price List', readonly=True)
    manufactured = fields.Float(string='Manufactured', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store Link', readonly=True)
    store_name = fields.Char(string='Store', readonly=True)
    stock_adjustment = fields.Float(string='Stock Adjustment', readonly=True)
    date = fields.Datetime(string='Date', readonly=True)
    doc_no = fields.Char(string='Reference / Doc No', readonly=True)
    type = fields.Char(string='Transaction Type', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)
    create_date = fields.Datetime(string='Created On', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    sl.id as id,
                    sl.product_id as product_id,
                    p.item_code as item_code,
                    p.name as item_name,
                    p.category_id as category_id,
                    (sl.balance_qty - sl.in_qty + sl.out_qty) as opening_stock,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%purchase%%' OR LOWER(sl.type) LIKE '%%puchase%%' THEN sl.in_qty 
                        ELSE 0.0 
                    END as purchases,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%transfer%%' THEN (CASE WHEN sl.in_qty > 0 THEN sl.in_qty ELSE sl.out_qty END)
                        ELSE 0.0 
                    END as transfers,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%sale%%' THEN (CASE WHEN sl.out_qty > 0 THEN sl.out_qty ELSE -sl.in_qty END)
                        ELSE 0.0 
                    END as qty_sold,
                    sl.balance_qty as closing_stock,
                    s.pricelist_id as pricelist_id,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%manufactur%%' OR LOWER(sl.type) LIKE '%%production%%' THEN sl.in_qty 
                        ELSE 0.0 
                    END as manufactured,
                    COALESCE(sl.store_id, st.id) as store_id,
                    COALESCE(st.name, sl.store) as store_name,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%adjust%%' OR LOWER(sl.type) LIKE '%%opening%%' THEN (CASE WHEN sl.in_qty > 0 THEN sl.in_qty ELSE -sl.out_qty END)
                        ELSE 0.0 
                    END as stock_adjustment,
                    sl.create_date as date,
                    sl.doc_no as doc_no,
                    sl.type as type,
                    COALESCE(sl.tenant_id, p.tenant_id, st.tenant_id) as tenant_id,
                    sl.create_uid as create_uid,
                    sl.create_date as create_date
                FROM
                    havanoposdesk_stock_ledger sl
                JOIN
                    havanoposdesk_product p ON p.id = sl.product_id
                LEFT JOIN
                    havanoposdesk_store st ON (sl.store_id = st.id OR (st.name = sl.store AND st.tenant_id = COALESCE(sl.tenant_id, p.tenant_id)))
                LEFT JOIN
                    havanoposdesk_sale s ON (s.name = sl.doc_no AND s.tenant_id = COALESCE(sl.tenant_id, p.tenant_id))
            )
        """ % (self._table,))

    @api.model
    def formatted_read_group(self, domain, groupby=(), aggregates=(), having=(), offset=0, limit=None, order=None) -> list[dict]:
        result = super().formatted_read_group(
            domain, groupby, aggregates, having=having,
            offset=offset, limit=limit, order=order)

        has_opening = any('opening_stock' in agg for agg in aggregates)
        has_closing = any('closing_stock' in agg for agg in aggregates)

        if not (has_opening or has_closing) or not result:
            return result

        for group_line in result:
            group_extra = group_line.get('__extra_domain') or []
            group_domain = list(group_extra) + list(domain or [])
            try:
                query = self._search(group_domain)
                where_clause = query.where_clause if getattr(query, '_where_clauses', None) else tools.SQL("TRUE")
                sql = tools.SQL(
                    """
                    WITH sp_bounds AS (
                        SELECT 
                            COALESCE(store_id, 0) as s_id,
                            product_id,
                            (ARRAY_AGG(opening_stock ORDER BY date ASC, id ASC))[1] as sp_opening,
                            (ARRAY_AGG(closing_stock ORDER BY date DESC, id DESC))[1] as sp_closing
                        FROM %s
                        WHERE %s
                        GROUP BY COALESCE(store_id, 0), product_id
                    )
                    SELECT 
                        COALESCE(SUM(sp_opening), 0.0) as actual_opening,
                        COALESCE(SUM(sp_closing), 0.0) as actual_closing
                    FROM sp_bounds
                    """,
                    query.from_clause,
                    where_clause,
                )
                rows = self.env.execute_query(sql)
                actual_opening = rows[0][0] if rows else 0.0
                actual_closing = rows[0][1] if rows else 0.0
            except Exception:
                actual_opening = 0.0
                actual_closing = 0.0

            if has_opening:
                if 'opening_stock:sum' in group_line:
                    group_line['opening_stock:sum'] = actual_opening
                group_line['opening_stock'] = actual_opening

            if has_closing:
                if 'closing_stock:sum' in group_line:
                    group_line['closing_stock:sum'] = actual_closing
                group_line['closing_stock'] = actual_closing

        return result
