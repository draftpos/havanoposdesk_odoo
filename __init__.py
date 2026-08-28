from . import core
from . import accounts
from . import inventory
from . import sales
from . import suppliers
from . import controllers
from . import migrations
from . import manufacturing


def post_migrate(env):
    """
    After module upgrade: ensure every user with havano_role='admin' has
    base.group_erp_manager so the Settings icon is visible to Tenant Admins.
    Also ensure cashier users (havano_role='user') do NOT have that group.
    """
    # Ensure all users have email set (copy from login if blank/null)
    users_without_email = env['res.users'].search([('email', '=', False), ('login', 'like', '%@%')])
    for user in users_without_email:
        user.email = user.login

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
    env.cr.execute("""
        DELETE FROM ir_rule 
        WHERE name IN ('Havano Currency Isolation', 'Havano Currency Rate Isolation')
           OR model_id IN (SELECT id FROM ir_model WHERE model IN ('res.currency', 'res.currency.rate'));
    """)

    # Backfill tenant_id on currencies used by tenants as base or secondary currency
    env.cr.execute("""
        UPDATE res_currency c
        SET tenant_id = t.id
        FROM havanoposdesk_tenant t
        WHERE (t.currency_id = c.id OR t.global_secondary_currency_id = c.id)
          AND (c.tenant_id IS NULL OR c.tenant_id != t.id);
    """)

    # Backfill tenant_id on currencies used by tenant accounts
    env.cr.execute("""
        UPDATE res_currency c
        SET tenant_id = a.tenant_id
        FROM havanoposdesk_account a
        WHERE a.currency_id = c.id
          AND c.tenant_id IS NULL
          AND a.tenant_id IS NOT NULL;
    """)

    # Ensure rate tenant_id matches currency tenant_id
    env.cr.execute("""
        UPDATE res_currency_rate r
        SET tenant_id = c.tenant_id
        FROM res_currency c
        WHERE r.currency_id = c.id
          AND (r.tenant_id IS DISTINCT FROM c.tenant_id);
    """)

    # Backfill tenant_id on payments with related sale/account/customer/user
    env.cr.execute("""
        UPDATE havanoposdesk_payment p
        SET tenant_id = s.tenant_id
        FROM havanoposdesk_sale s
        WHERE p.sale_id = s.id AND p.tenant_id IS NULL AND s.tenant_id IS NOT NULL;
    """)
    env.cr.execute("""
        UPDATE havanoposdesk_payment p
        SET tenant_id = a.tenant_id
        FROM havanoposdesk_account a
        WHERE p.account_id = a.id AND p.tenant_id IS NULL AND a.tenant_id IS NOT NULL;
    """)
    env.cr.execute("""
        UPDATE havanoposdesk_payment p
        SET tenant_id = u.tenant_id
        FROM res_users u
        WHERE p.create_uid = u.id AND p.tenant_id IS NULL AND u.tenant_id IS NOT NULL;
    """)
    env.cr.execute("""
        UPDATE havanoposdesk_account a
        SET tenant_id = u.tenant_id
        FROM res_users u
        WHERE a.create_uid = u.id AND a.tenant_id IS NULL AND u.tenant_id IS NOT NULL;
    """)

    # Ensure global read access on res.currency and res.currency.rate in ir_model_access
    env.cr.execute("""
        INSERT INTO ir_model_access (name, model_id, perm_read, perm_write, perm_create, perm_unlink, active)
        SELECT 'res.currency global read', m.id, True, False, False, False, True
        FROM ir_model m
        WHERE m.model = 'res.currency'
        AND NOT EXISTS (
            SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.group_id IS NULL AND a.perm_read = True
        )
    """)
    env.cr.execute("""
        INSERT INTO ir_model_access (name, model_id, perm_read, perm_write, perm_create, perm_unlink, active)
        SELECT 'res.currency.rate global read', m.id, True, False, False, False, True
        FROM ir_model m
        WHERE m.model = 'res.currency.rate'
        AND NOT EXISTS (
            SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.group_id IS NULL AND a.perm_read = True
        )
    """)

    # Ensure all active users have base.group_user in res_groups_users_rel
    if internal_group:
        env.cr.execute("""
            INSERT INTO res_groups_users_rel (gid, uid)
            SELECT %s, u.id
            FROM res_users u
            WHERE u.active = True
              AND u.id NOT IN (
                  SELECT uid FROM res_groups_users_rel WHERE gid = %s
              );
        """, [internal_group.id, internal_group.id])

    # Ensure global read access on catalog/inventory models in ir_model_access
    catalog_models = [
        'havanoposdesk.category',
        'havanoposdesk.uom',
        'havanoposdesk.product',
        'havanoposdesk.pricelist',
        'havanoposdesk.product.uom.price',
        'havanoposdesk.stock.valuation',
        'havanoposdesk.stock.ledger',
        'havanoposdesk.store'
    ]
    for model_name in catalog_models:
        env.cr.execute("""
            INSERT INTO ir_model_access (name, model_id, perm_read, perm_write, perm_create, perm_unlink, active)
            SELECT %s || ' global read', m.id, True, False, False, False, True
            FROM ir_model m
            WHERE m.model = %s
            AND NOT EXISTS (
                SELECT 1 FROM ir_model_access a WHERE a.model_id = m.id AND a.group_id IS NULL AND a.perm_read = True
            );
        """, [model_name, model_name])

    # Update Category, UOM, and Pricelist Isolation Rules so all users in the tenant can read catalog records
    env.cr.execute("""
        UPDATE ir_rule
        SET domain_force = '[] if user.havano_role == ''super_admin'' or not user.tenant_id else [''|'', (''tenant_id'', ''='', False), (''tenant_id'', ''='', user.tenant_id.id)]'
        WHERE name IN ('Havano Category Isolation', 'Havano UOM Isolation', 'Havano Pricelist Isolation', 'Havano Product UOM Price Isolation');
    """)

    env.registry.clear_cache()




