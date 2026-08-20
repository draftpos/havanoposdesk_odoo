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
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='Currency for prices in this pricelist. If not set, the base currency is assumed.',
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id and self.env.user.tenant_id.currency_id else False,
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

    @api.model
    def name_search(self, name='', domain=None, operator='ilike', limit=100):
        if self.env.context.get('import_file') and operator == '=':
            operator = 'ilike'
        return super().name_search(name=name, domain=domain, operator=operator, limit=limit)

