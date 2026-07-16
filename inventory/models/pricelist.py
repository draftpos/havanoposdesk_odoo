from odoo import models, fields, api

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
                    raise ValidationError(f"A Pricelist with the name '{record.name}' already exists in your workspace. Please choose a different name.")
