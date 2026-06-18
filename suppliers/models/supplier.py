from odoo import models, fields

class HavanoposdeskSupplier(models.Model):
    _name = 'havanoposdesk.supplier'
    _description = 'Supplier'

    name = fields.Char(string='Supplier Name', required=True)
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    address = fields.Text(string='Address')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one(
        'havanoposdesk.store', 
        string='Store', 
        required=True, 
        default=lambda self: self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1).id
    )
