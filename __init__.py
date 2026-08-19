from . import core
from . import accounts
from . import inventory
from . import sales
from . import suppliers
from . import controllers


def post_migrate(cr, registry):
    """
    After module upgrade: ensure every user with havano_role='admin' has
    base.group_erp_manager so the Settings icon is visible to Tenant Admins.
    Also ensure cashier users (havano_role='user') do NOT have that group.
    """
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})

    # Ensure all users have email set (copy from login if blank/null)
    cr.execute("UPDATE res_users SET email = login WHERE (email IS NULL OR email = '') AND login LIKE '%@%'")

    erp_manager_group = env.ref('base.group_erp_manager', raise_if_not_found=False)
    tenant_admin_group = env.ref('havanoposdesk_odoo.group_tenant_admin', raise_if_not_found=False)
    group_system = env.ref('base.group_system', raise_if_not_found=False)
    internal_group = env.ref('base.group_user', raise_if_not_found=False)
    portal_group = env.ref('base.group_portal', raise_if_not_found=False)
    public_group = env.ref('base.group_public', raise_if_not_found=False)

    # Ensure all tenant users (super_admin, admin, user) have base.group_user and no portal/public groups
    all_erp_users = env['res.users'].with_context(active_test=False).search([
        '|', ('tenant_id', '!=', False), ('havano_role', 'in', ('super_admin', 'admin', 'user'))
    ])
    for user in all_erp_users:
        group_cmds = []
        if portal_group and portal_group in user.group_ids:
            group_cmds.append((3, portal_group.id, 0))
        if public_group and public_group in user.group_ids:
            group_cmds.append((3, public_group.id, 0))
        if internal_group and internal_group not in user.group_ids:
            group_cmds.append((4, internal_group.id, 0))
        if group_cmds:
            user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})

    # Grant Administration Settings group to all super admins
    if group_system:
        super_admins = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'super_admin')])
        for user in super_admins:
            if group_system not in user.group_ids:
                user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': [(4, group_system.id, 0)]})

    if erp_manager_group:
        # Grant Settings group to all tenant admins
        admins = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'admin')])
        for user in admins:
            group_cmds = []
            if erp_manager_group not in user.group_ids:
                group_cmds.append((4, erp_manager_group.id, 0))
            if tenant_admin_group and tenant_admin_group not in user.group_ids:
                group_cmds.append((4, tenant_admin_group.id, 0))
            if group_cmds:
                user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})

        # Strip Settings group from cashiers
        cashiers = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'user')])
        for user in cashiers:
            group_cmds = []
            if erp_manager_group in user.group_ids:
                group_cmds.append((3, erp_manager_group.id, 0))
            if tenant_admin_group and tenant_admin_group in user.group_ids:
                group_cmds.append((3, tenant_admin_group.id, 0))
            if group_cmds:
                user.sudo().with_context(bypass_sync_role_groups=True).write({'group_ids': group_cmds})

    # Seed missing accounts/payment methods for all existing tenants
    tenants = env['havanoposdesk.tenant'].with_context(active_test=False).search([])
    for tenant in tenants:
        try:
            tenant._seed_default_data()
        except Exception:
            pass

    # Clean up any leftover currency isolation record rules in ir_rule table
    cr.execute("""
        DELETE FROM ir_rule 
        WHERE name IN ('Havano Currency Isolation', 'Havano Currency Rate Isolation')
           OR model_id IN (SELECT id FROM ir_model WHERE model IN ('res.currency', 'res.currency.rate'));
    """)

    # Reset tenant_id to NULL on global currencies and rates so all users/tenants can access standard currencies
    cr.execute("UPDATE res_currency SET tenant_id = NULL WHERE tenant_id IS NOT NULL;")
    cr.execute("UPDATE res_currency_rate SET tenant_id = NULL WHERE tenant_id IS NOT NULL;")

    # Ensure global read access on res.currency and res.currency.rate in ir_model_access
    cr.execute("""
        INSERT INTO ir_model_access (name, model_id, perm_read, perm_write, perm_create, perm_unlink, active)
        SELECT 'res.currency global read', m.id, True, False, False, False, True
        FROM ir_model m
        WHERE m.model = 'res.currency'
        AND NOT EXISTS (
            SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.group_id IS NULL AND a.perm_read = True
        )
    """)
    cr.execute("""
        INSERT INTO ir_model_access (name, model_id, perm_read, perm_write, perm_create, perm_unlink, active)
        SELECT 'res.currency.rate global read', m.id, True, False, False, False, True
        FROM ir_model m
        WHERE m.model = 'res.currency.rate'
        AND NOT EXISTS (
            SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.group_id IS NULL AND a.perm_read = True
        )
    """)
    if 'ir.model.access' in env:
        env['ir.model.access'].call_cache_clearing_methods()
    if 'ir.rule' in env:
        env['ir.rule'].clear_caches()
    env.registry.clear_cache()




