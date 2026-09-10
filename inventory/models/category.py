from odoo import models, fields, api

class HavanoposdeskCategory(models.Model):
    _name = 'havanoposdesk.category'
    _description = 'Category'

    _constraints = [
        models.Constraint('unique (name, tenant_id)', 'Category name must be unique per tenant!')
    ]

    name = fields.Char(string='Category Name', required=True)
    not_for_pos = fields.Boolean(string='Not For POS', default=False)
    store_ids = fields.Many2many('havanoposdesk.store', string='Stores', required=False, default=lambda self: self._default_store_ids())
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self._default_tenant_id())

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
        return super().create(vals_list)

    def _default_store_ids(self):
        # Prevent accessing env.user during registry load
        if self.env.registry.ready and self.env.user.default_store_id:
            return [(6, 0, [self.env.user.default_store_id.id])]
        return False

    def _default_tenant_id(self):
        if self.env.registry.ready:
            return self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
        return False

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
                if self.sudo().search_count(domain) > 0:
                    raise ValidationError(f"A Category with the name '{record.name}' already exists in your workspace. Please choose a different name.")

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('import_file') and operator == '=':
            operator = 'ilike'
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

