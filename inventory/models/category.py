from odoo import models, fields

class HavanoposdeskCategory(models.Model):
    _name = 'havanoposdesk.category'
    _description = 'Category'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Category name must be unique per tenant!')
    ]

    name = fields.Char(string='Category Name', required=True)
    is_main_category = fields.Boolean(string='Is Main Category', default=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store')

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id)
