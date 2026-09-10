from odoo import models, fields, tools

class ItemSummaryLedgerReport(models.Model):
    _name = 'havanoposdesk.item.summary.ledger.report'
    _description = 'Item Summary Ledger Report'
    _auto = False

    product_id = fields.Many2one('havanoposdesk.product', string='Item', readonly=True)
    item_code = fields.Char(string='Item Code', readonly=True)
    item_name = fields.Char(string='Item Name', readonly=True)
    category_id = fields.Many2one('havanoposdesk.category', string='Item Group', readonly=True)
    opening_stock = fields.Float(string='Opening Stock', readonly=True)
    qty_in = fields.Float(string='In', readonly=True)
    qty_out = fields.Float(string='Out', readonly=True)
    closing_stock = fields.Float(string='Closing Stock', readonly=True)
    pricelist_id = fields.Many2one('havanoposdesk.pricelist', string='Price List', readonly=True)
    manufactured = fields.Float(string='Manufactured', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store Link', readonly=True)
    store_name = fields.Char(string='Store', readonly=True)
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
                    sl.in_qty as qty_in,
                    sl.out_qty as qty_out,
                    sl.balance_qty as closing_stock,
                    s.pricelist_id as pricelist_id,
                    CASE 
                        WHEN LOWER(sl.type) LIKE '%%manufactur%%' OR LOWER(sl.type) LIKE '%%production%%' THEN sl.in_qty 
                        ELSE 0.0 
                    END as manufactured,
                    COALESCE(sl.store_id, st.id) as store_id,
                    COALESCE(st.name, sl.store) as store_name,
                    sl.create_date as date,
                    sl.doc_no as doc_no,
                    sl.type as type,
                    sl.tenant_id as tenant_id,
                    sl.create_uid as create_uid,
                    sl.create_date as create_date
                FROM
                    havanoposdesk_stock_ledger sl
                JOIN
                    havanoposdesk_product p ON p.id = sl.product_id
                LEFT JOIN
                    havanoposdesk_store st ON (sl.store_id = st.id OR (st.name = sl.store AND st.tenant_id = sl.tenant_id))
                LEFT JOIN
                    havanoposdesk_sale s ON (s.name = sl.doc_no AND s.tenant_id = sl.tenant_id)
            )
        """ % (self._table,))
