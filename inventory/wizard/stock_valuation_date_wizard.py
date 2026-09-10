from odoo import models, fields, api, _
from datetime import datetime

class StockValuationDateWizard(models.TransientModel):
    _name = 'havanoposdesk.stock.valuation.date.wizard'
    _description = 'Stock Valuation By Date Wizard'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        ondelete='cascade',
        default=lambda self: self.env.user.tenant_id.id
    )
    date_to = fields.Date(string='Date To', required=True, default=fields.Date.context_today)
    store_id = fields.Many2one(
        'havanoposdesk.store', 
        string='Store', 
        required=False,
        domain="[('tenant_id', '=', tenant_id)] if tenant_id else []",
        help="Leave empty to calculate for all stores."
    )

    def action_compute(self):
        self.ensure_one()
        
        # We need to query havanoposdesk.stock.ledger
        # for in_qty and out_qty up to date_to.
        date_to_dt = datetime.combine(self.date_to, datetime.max.time())
        
        domain = [
            ('tenant_id', '=', self.tenant_id.id),
            ('create_date', '<=', date_to_dt)
        ]
        if self.store_id:
            domain.append(('store_id', '=', self.store_id.id))
        
        ledgers = self.env['havanoposdesk.stock.ledger'].search(domain)
        
        # Group by product and store
        stock_data = {}
        for line in ledgers:
            key = (line.product_id.id, line.store_id.id, line.store)
            if key not in stock_data:
                stock_data[key] = {
                    'product_id': line.product_id.id,
                    'store_id': line.store_id.id,
                    'store': line.store,
                    'on_hand_qty': 0.0,
                    'buying_price': line.product_id.buying_price,
                    'selling_price': line.product_id.selling_price,
                }
            stock_data[key]['on_hand_qty'] += (line.in_qty - line.out_qty)
        
        # Create report records
        report_obj = self.env['havanoposdesk.stock.valuation.date.report']
        # clear previous records for this user to keep it clean
        old_reports = report_obj.search([('create_uid', '=', self.env.uid)])
        old_reports.unlink()
        
        report_lines = []
        for key, data in stock_data.items():
            report_lines.append({
                'wizard_id': self.id,
                'tenant_id': self.tenant_id.id,
                'product_id': data['product_id'],
                'store_id': data['store_id'],
                'store': data['store'],
                'on_hand_qty': data['on_hand_qty'],
                'value_cost': data['on_hand_qty'] * data['buying_price'],
                'value_selling': data['on_hand_qty'] * data['selling_price'],
            })
            
        report_obj.create(report_lines)
        
        return {
            'name': _('Stock Valuation as of %s') % self.date_to,
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.stock.valuation.date.report',
            'view_mode': 'list,pivot',
            'domain': [('wizard_id', '=', self.id)],
            'context': {'search_default_group_by_store': 1},
        }

class StockValuationDateReport(models.TransientModel):
    _name = 'havanoposdesk.stock.valuation.date.report'
    _description = 'Stock Valuation By Date Report'
    
    wizard_id = fields.Many2one('havanoposdesk.stock.valuation.date.wizard', string='Wizard Reference', ondelete='cascade')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', ondelete='cascade')
    currency_id = fields.Many2one(related='tenant_id.currency_id', store=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Product', ondelete='cascade')
    item_name = fields.Char(related='product_id.name', string='Item Name', store=True)
    item_code = fields.Char(related='product_id.item_code', string='Code', store=True)
    category_id = fields.Many2one(related='product_id.category_id', string='Category', store=True)
    store = fields.Char(string='Store')
    store_id = fields.Many2one('havanoposdesk.store', string='Store Link', ondelete='cascade')
    on_hand_qty = fields.Float(string='On Hand Qty')
    value_cost = fields.Float(string='Value Cost')
    value_selling = fields.Float(string='Value Selling')
