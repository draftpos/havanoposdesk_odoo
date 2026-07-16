from odoo import models, fields, api

class HavanoposdeskUom(models.Model):
    _name = 'havanoposdesk.uom'
    _description = 'Uom'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'UOM name must be unique per tenant!')
    ]

    name = fields.Char(string='UOM Name', required=True)
    
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
                    raise ValidationError(f"A UOM with the name '{record.name}' already exists in your workspace. Please choose a different name.")
