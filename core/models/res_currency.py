from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCurrency(models.Model):
    _inherit = 'res.currency'

    @api.model
    def _get_conversion_rate(self, from_currency, to_currency, company=None, date=None):
        if not from_currency or not to_currency or from_currency == to_currency:
            return 1.0
        if from_currency.name and to_currency.name and from_currency.name.strip().upper() == to_currency.name.strip().upper():
            return 1.0
        tenant = self.env.user.tenant_id if hasattr(self.env, 'user') and self.env.user else False
        if tenant and tenant.currency_id:
            base_name = tenant.currency_id.name.strip().upper() if tenant.currency_id.name else ''
            if from_currency.name and to_currency.name and from_currency.name.strip().upper() == base_name and to_currency.name.strip().upper() == base_name:
                return 1.0
        return super()._get_conversion_rate(from_currency, to_currency, company=company, date=date)

    @api.model
    def _validate_tenant_currency(self, currency, tenant):
        currency = self.browse(currency) if isinstance(currency, int) else currency
        if not currency or not tenant:
            return currency
            
        # If the currency already belongs to this tenant or is global (tenant_id is False), it is valid
        if not currency.tenant_id or currency.tenant_id == tenant:
            return currency

        clean_name = (currency.name or '').strip()
        if not clean_name:
            return currency

        # Look for an existing currency for this tenant
        tenant_curr = self.sudo().search([
            ('tenant_id', '=', tenant.id),
            ('name', '=ilike', clean_name)
        ], limit=1)
        if tenant_curr:
            return tenant_curr

        # Look for a global currency with the same name
        global_curr = self.sudo().search([
            ('tenant_id', '=', False),
            ('name', '=ilike', clean_name)
        ], limit=1)
        if global_curr:
            return global_curr

        # Auto-create the currency for this tenant
        try:
            return self.sudo().create({
                'name': currency.name,
                'symbol': currency.symbol or currency.name,
                'full_name': getattr(currency, 'full_name', currency.name) or currency.name,
                'rounding': currency.rounding or 0.01,
                'decimal_places': currency.decimal_places or 2,
                'active': True,
                'tenant_id': tenant.id,
            })
        except Exception:
            fallback = self.sudo().search([
                ('tenant_id', '=', tenant.id),
                ('name', '=ilike', clean_name)
            ], limit=1)
            return fallback or currency

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        default=lambda self: self.env.user.tenant_id.id if self.env.user.tenant_id else False,
        index=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
        return super().create(vals_list)

    is_base_currency = fields.Boolean(
        string='Base Currency',
        compute='_compute_is_base_currency',
        store=False,
        help='Indicates if this is the base (default) currency for your business.',
    )

    @api.depends_context('uid')
    def _compute_is_base_currency(self):
        tenant = self.env.user.tenant_id
        base_currency_id = tenant.currency_id.id if tenant and tenant.currency_id else False
        for rec in self:
            rec.is_base_currency = (rec.id == base_currency_id) if base_currency_id else False

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

    def _check_access(self, operation: str):
        if operation == 'read':
            return None
        return super()._check_access(operation)

    def check_access(self, operation: str) -> None:
        if operation == 'read':
            return None
        return super().check_access(operation)

    def check_access_rights(self, operation, raise_exception=True):
        if operation == 'read':
            return True
        return super().check_access_rights(operation, raise_exception=raise_exception)

