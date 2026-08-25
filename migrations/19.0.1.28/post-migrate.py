"""Remove invalid currency relation domains from category record rules."""
from odoo import SUPERUSER_ID, api


CATEGORY_DOMAIN = (
    "[] if user.havano_role == 'super_admin' or not user.tenant_id else "
    "[('tenant_id', '=', user.tenant_id.id), '|', ('store_ids', '=', False), "
    "('store_ids', 'in', user.store_ids.ids)] if "
    "(user.havano_role == 'admin' and user.store_ids) or user.havano_role == 'user' "
    "else [('tenant_id', '=', user.tenant_id.id)]"
)


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    category_model = env['ir.model']._get('havanoposdesk.category')
    rules = env['ir.rule'].search([
        ('model_id', '=', category_model.id),
        ('domain_force', 'like', 'currency_id.tenant_id'),
    ])
    if rules:
        rules.write({'domain_force': CATEGORY_DOMAIN})
