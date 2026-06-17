from odoo import models, fields, api

class HavanoposdeskSale(models.Model):
    _name = 'havanoposdesk.sale'
    _description = 'Sale'
    _order = 'date desc, id desc'

    name = fields.Char(string='Sale Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
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
    date = fields.Datetime(string='Sale Date', default=fields.Datetime.now, required=True)
    amount_total = fields.Float(string='Total Amount', required=True, default=0.0)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user.id)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done')
    ], string='Status', default='draft', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale') or 'New'
        return super().create(vals_list)
