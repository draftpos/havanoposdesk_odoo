"""
Migration: sync group_erp_manager for all existing users based on havano_role.
- Admin users  → get group_erp_manager + group_tenant_admin
- Cashier users → stripped of group_erp_manager + group_tenant_admin
"""
from odoo import api, SUPERUSER_ID


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})

    erp_manager_group = env.ref('base.group_erp_manager', raise_if_not_found=False)
    tenant_admin_group = env.ref('havanoposdesk_odoo.group_tenant_admin', raise_if_not_found=False)

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

    # Strip Settings and Tenant Admin groups from cashiers
    cashiers = env['res.users'].with_context(active_test=False).search([('havano_role', '=', 'user')])
    for user in cashiers:
        group_cmds = []
        if erp_manager_group in user.group_ids:
            group_cmds.append((3, erp_manager_group.id, 0))
        if tenant_admin_group and tenant_admin_group in user.group_ids:
            group_cmds.append((3, tenant_admin_group.id, 0))
        if group_cmds:
            user.sudo().write({'group_ids': group_cmds})

