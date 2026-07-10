from odoo import models, fields

class HavanoposdeskPricelist(models.Model):
    _name = 'havanoposdesk.pricelist'
    _description = 'Pricelist'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Pricelist name must be unique per tenant!')
    ]

    name = fields.Char(string='Pricelist Name', required=True)
    type = fields.Selection([
        ('selling', 'Selling'),
        ('buying', 'Buying')
    ], string='Type', required=True, default='selling')

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        required=True,
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
