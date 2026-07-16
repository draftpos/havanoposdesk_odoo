from odoo import models, fields, api

class HavanoposdeskCategory(models.Model):
    _name = 'havanoposdesk.category'
    _description = 'Category'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Category name must be unique per tenant!')
    ]

    name = fields.Char(string='Category Name', required=True)
    store_ids = fields.Many2many('havanoposdesk.store', string='Stores', required=True, default=lambda self: [(6, 0, [self.env.user.default_store_id.id])] if self.env.user.default_store_id else False)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id)

    @api.constrains('name', 'tenant_id')
    def _check_unique_name(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.name and record.tenant_id:
                domain = [
                    ('id', '!=', record.id),
                    ('tenant_id', '=', record.tenant_id.id),
                    ('name', '=ilike', record.name.strip())
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(f"A Category with the name '{record.name}' already exists in your workspace. Please choose a different name.")
