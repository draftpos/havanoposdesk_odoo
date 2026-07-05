from . import core
from . import accounts
from . import inventory
from . import sales
from . import suppliers


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

    # Grant Administration Settings group to all super admins
    if group_system:
        super_admins = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'super_admin')])
        for user in super_admins:
            if group_system not in user.group_ids:
                user.sudo().write({'group_ids': [(4, group_system.id, 0)]})

    if not erp_manager_group:
        return

    # Grant Settings group to all tenant admins
    admins = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'admin')])
    for user in admins:
        group_cmds = []
        if erp_manager_group not in user.group_ids:
            group_cmds.append((4, erp_manager_group.id, 0))
        if tenant_admin_group and tenant_admin_group not in user.group_ids:
            group_cmds.append((4, tenant_admin_group.id, 0))
        if group_cmds:
            user.sudo().write({'group_ids': group_cmds})

    # Strip Settings group from cashiers
    cashiers = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'user')])
    for user in cashiers:
        group_cmds = []
        if erp_manager_group in user.group_ids:
            group_cmds.append((3, erp_manager_group.id, 0))
        if tenant_admin_group and tenant_admin_group in user.group_ids:
            group_cmds.append((3, tenant_admin_group.id, 0))
        if group_cmds:
            user.sudo().write({'group_ids': group_cmds})

