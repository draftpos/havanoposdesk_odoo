from odoo import models, fields, api

class HavanoposdeskPurchase(models.Model):
    _name = 'havanoposdesk.purchase'
    _description = 'Purchase'
    _order = 'date desc, id desc'

    name = fields.Char(string='Purchase Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    shop_id = fields.Many2one(
        'havanoposdesk.shop', 
        string='Shop', 
        required=True, 
        default=lambda self: self.env.user.default_shop_id.id or self.env['havanoposdesk.shop'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1).id
    )
    date = fields.Datetime(string='Purchase Date', default=fields.Datetime.now, required=True)
    amount_total = fields.Float(string='Total Amount', required=True, default=0.0)
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done')
    ], string='Status', default='draft', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.purchase') or 'New'
        return super().create(vals_list)
