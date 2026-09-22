from odoo import models, fields, tools

class PurchasesItemTaxReport(models.Model):
    _name = 'havanoposdesk.purchases.item.tax.report'
    _description = 'Purchases Item Tax Report'
    _auto = False
    _order = 'date desc, id desc'

    product_id = fields.Many2one('havanoposdesk.product', string='Product', readonly=True)
    name = fields.Char(string='Item Name', readonly=True)
    item_code = fields.Char(string='Item Code', readonly=True)
    hs_code = fields.Char(string='HS Code', readonly=True)
    category_id = fields.Many2one('havanoposdesk.category', string='Category', readonly=True)
    qty = fields.Float(string='Qty', readonly=True)
    total_exclu = fields.Monetary(string='Total Exclu', readonly=True, currency_field='currency_id')
    total_tax = fields.Monetary(string='Total Tax', readonly=True, currency_field='currency_id')
    total_inclu = fields.Monetary(string='Total Inclu', readonly=True, currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', string='Currency', readonly=True)
    
    # Document (Original Transaction) Currency fields
    doc_currency_id = fields.Many2one('res.currency', string='Doc Currency', readonly=True)
    exchange_rate = fields.Float(string='Exchange Rate', readonly=True)
    doc_total_exclu = fields.Monetary(string='Doc Total Exclu', readonly=True, currency_field='doc_currency_id')
    doc_total_tax = fields.Monetary(string='Doc Total Tax', readonly=True, currency_field='doc_currency_id')
    doc_total_inclu = fields.Monetary(string='Doc Total Inclu', readonly=True, currency_field='doc_currency_id')
    
    date = fields.Date(string='Date', readonly=True)
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier', readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True, index=True)
    create_uid = fields.Many2one('res.users', string='Created By', readonly=True)
    create_date = fields.Datetime(string='Created On', readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW %s AS (
                SELECT
                    l.id as id,
                    l.product_id as product_id,
                    p.name as name,
                    p.item_code as item_code,
                    p.hs_code as hs_code,
                    p.category_id as category_id,
                    s.store_id as store_id,
                    s.supplier as supplier_id,
                    COALESCE(t.currency_id, s.currency_id) as currency_id,
                    s.currency_id as doc_currency_id,
                    COALESCE(NULLIF(s.exchange_rate, 0), 1.0) as exchange_rate,
                    l.tenant_id as tenant_id,
                    s.posting_date as date,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.accepted_qty, 0.0)) 
                        ELSE ABS(COALESCE(l.accepted_qty, 0.0)) 
                    END as qty,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.price_subtotal, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                        ELSE ABS(COALESCE(l.price_subtotal, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                    END as total_exclu,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.price_tax, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                        ELSE ABS(COALESCE(l.price_tax, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                    END as total_tax,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.amount, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                        ELSE ABS(COALESCE(l.amount, 0.0) / COALESCE(NULLIF(s.exchange_rate, 0), 1.0))
                    END as total_inclu,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.price_subtotal, 0.0))
                        ELSE ABS(COALESCE(l.price_subtotal, 0.0))
                    END as doc_total_exclu,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.price_tax, 0.0))
                        ELSE ABS(COALESCE(l.price_tax, 0.0))
                    END as doc_total_tax,
                    CASE 
                        WHEN s.is_return THEN -ABS(COALESCE(l.amount, 0.0))
                        ELSE ABS(COALESCE(l.amount, 0.0))
                    END as doc_total_inclu,
                    s.create_uid as create_uid,
                    s.create_date as create_date
                FROM
                    havanoposdesk_purchase_line l
                JOIN
                    havanoposdesk_product p ON p.id = l.product_id
                JOIN
                    havanoposdesk_purchase s ON s.id = l.purchase_id
                LEFT JOIN
                    havanoposdesk_tenant t ON t.id = l.tenant_id
                WHERE
                    s.state = 'posted'
            )
        """ % (self._table,))
