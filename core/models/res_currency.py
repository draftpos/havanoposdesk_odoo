from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        default=lambda self: self.env.user.tenant_id.id if self.env.user.tenant_id else False,
        index=True
    )

    _unique_name = models.Constraint(
        'unique (name, tenant_id)',
        "The currency code must be unique per tenant!",
    )

    @api.constrains('name', 'tenant_id')
    def _check_unique_currency_name_per_tenant(self):
        for record in self:
            if record.name:
                clean_name = record.name.strip()
                domain = [
                    ('id', '!=', record.id),
                    ('name', '=ilike', clean_name),
                ]
                if record.tenant_id:
                    domain.append(('tenant_id', '=', record.tenant_id.id))
                else:
                    domain.append(('tenant_id', '=', False))
                if self.search_count(domain) > 0:
                    raise ValidationError(_("A currency with the code '%s' already exists for this tenant.") % clean_name)
