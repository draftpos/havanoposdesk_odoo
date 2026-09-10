"""
Migration 19.0.1.37:
1. Normalize user roles in res_users (non-admin -> 'user'/Cashier).
2. Normalize roles in havanoposdesk_user_rights_profile ('cashier' -> 'user').
3. Auto-link all tenant users to their default User Rights Profile.
4. Update cashier profile permissions with activated rights for POS, Dashboard, Reports, Settings, Sales, Quotations, Customers, Expenses, Printer.
5. Populate all missing feature permissions.
"""
from odoo import SUPERUSER_ID, api
import logging

_logger = logging.getLogger(__name__)

ALL_POS_FEATURES = [
    'Dashboard', 'POS', 'Quotations', 'Sales', 'Products',
    'Categories', 'Brands', 'Taxes', 'Stock Management',
    'Payment Entries', 'Reports', 'Profit and Loss', 'Settings',
    'Printer', 'Terminals', 'Stores', 'Suppliers', 'Customers',
    'Expenses', 'Payroll', 'User Profiles'
]

CASHIER_FULL_FEATURES = (
    'POS', 'Dashboard', 'Reports', 'Settings',
    'Sales', 'Quotations', 'Customers', 'Expenses', 'Printer'
)

CASHIER_READ_FEATURES = {
    'Products', 'Categories', 'Brands', 'Taxes',
    'Stock Management', 'Payment Entries', 'Stores', 'Terminals', 'Suppliers'
}


def migrate(cr, version):
    _logger.info("=== [HAVANO MIGRATION 19.0.1.37] Starting User Rights & Role Migration ===")

    # 1. Update non-admin users in res_users to have havano_role = 'user' (Cashier)
    cr.execute("""
        UPDATE res_users
        SET havano_role = 'user'
        WHERE id != 1
          AND (havano_role IS NULL OR havano_role NOT IN ('admin', 'super_admin'))
          AND tenant_id IS NOT NULL;
    """)
    _logger.info("Updated non-admin res_users to havano_role='user'")

    # 2. Normalize legacy 'cashier' role strings on profiles to 'user'
    cr.execute("""
        UPDATE havanoposdesk_user_rights_profile
        SET havano_role = 'user'
        WHERE havano_role = 'cashier';
    """)
    _logger.info("Normalized havanoposdesk_user_rights_profile roles")

    # 3. Ensure every tenant has default profiles (Super Admin, Admin, Cashier)
    env = api.Environment(cr, SUPERUSER_ID, {})
    tenants = env['havanoposdesk.tenant'].with_context(active_test=False).search([])
    for tenant in tenants:
        profiles_to_check = [
            ('Super Admin Profile', 'super_admin'),
            ('Admin Profile', 'admin'),
            ('Cashier Profile', 'user'),
        ]
        for prof_name, role in profiles_to_check:
            existing = env['havanoposdesk.user.rights.profile'].search([
                ('tenant_id', '=', tenant.id),
                '|', ('name', '=ilike', prof_name), ('havano_role', '=', role)
            ], limit=1)
            if not existing:
                env['havanoposdesk.user.rights.profile'].create({
                    'name': prof_name,
                    'tenant_id': tenant.id,
                    'havano_role': role,
                    'is_default': True,
                })

    # 4. Activate full cashier rights on core features (POS, Dashboard, Reports, Settings, Sales, Quotations, Customers, Expenses, Printer)
    cr.execute("""
        UPDATE havanoposdesk_user_rights_permission p
        SET can_read = True,
            can_create = True,
            can_update = True,
            can_delete = True,
            can_submit = True
        FROM havanoposdesk_user_rights_profile prof
        WHERE p.profile_id = prof.id
          AND (prof.havano_role IN ('user', 'cashier') OR prof.name ILIKE '%%Cashier%%')
          AND p.feature IN %s
    """, (CASHIER_FULL_FEATURES,))
    _logger.info("Activated full permissions for cashier features in database")

    # 5. Ensure all admin profile permissions are fully activated
    cr.execute("""
        UPDATE havanoposdesk_user_rights_permission p
        SET can_read = True,
            can_create = True,
            can_update = True,
            can_delete = True,
            can_submit = True
        FROM havanoposdesk_user_rights_profile prof
        WHERE p.profile_id = prof.id
          AND prof.havano_role IN ('admin', 'super_admin');
    """)
    _logger.info("Activated full permissions for admin profiles in database")

    # 6. Auto-link any user missing user_rights_profile_id to their tenant profile
    cr.execute("""
        UPDATE res_users u
        SET user_rights_profile_id = (
            SELECT p.id FROM havanoposdesk_user_rights_profile p
            WHERE p.tenant_id = u.tenant_id
              AND (p.havano_role = u.havano_role OR (u.havano_role = 'user' AND p.havano_role IN ('user', 'cashier')))
            ORDER BY p.is_default DESC, p.id ASC
            LIMIT 1
        )
        WHERE u.tenant_id IS NOT NULL
          AND (
              u.user_rights_profile_id IS NULL
              OR u.user_rights_profile_id NOT IN (
                  SELECT id FROM havanoposdesk_user_rights_profile WHERE tenant_id = u.tenant_id
              )
          );
    """)
    _logger.info("Auto-linked res_users to default user_rights_profile_id")

    # 7. Populate any missing feature permissions for all profiles
    all_profiles = env['havanoposdesk.user.rights.profile'].with_context(active_test=False).search([])
    cashier_full_set = set(CASHIER_FULL_FEATURES)
    for prof in all_profiles:
        is_cashier = prof.havano_role in ('user', 'cashier') or 'cashier' in (prof.name or '').lower()
        existing_feats = prof.permission_ids.mapped('feature')
        for f in ALL_POS_FEATURES:
            if f not in existing_feats:
                if is_cashier:
                    is_full = f in cashier_full_set
                    is_read = is_full or (f in CASHIER_READ_FEATURES)
                    env['havanoposdesk.user.rights.permission'].create({
                        'profile_id': prof.id,
                        'feature': f,
                        'can_read': is_read,
                        'can_create': is_full,
                        'can_update': is_full,
                        'can_delete': is_full,
                        'can_submit': is_full,
                    })
                else:
                    env['havanoposdesk.user.rights.permission'].create({
                        'profile_id': prof.id,
                        'feature': f,
                        'can_read': True,
                        'can_create': True,
                        'can_update': True,
                        'can_delete': True,
                        'can_submit': True,
                    })

    env.registry.clear_cache()
    _logger.info("=== [HAVANO MIGRATION 19.0.1.37] Completed Successfully ===")
