# Changelog - `havanoposdesk_odoo`

All notable changes to the `havanoposdesk_odoo` module are documented in this file.

---

## [2026-09-04] - Multi-Store Cashier Support & API Enhancements

### Added / Modified
1. **`core/models/res_users.py`**:
   - Removed single-store truncation in `_check_store_access_limit`, `_onchange_default_store_id`, `_onchange_store_ids`, and `_onchange_havano_role_profile`.
   - Cashiers (`havano_role = 'user'`) can now hold multiple authorized stores in `store_ids`.

2. **`inventory/controllers/api.py`**:
   - **`/api/users` & `/api/user/login`**:
     - `warehouse` serialized as comma-separated allowed stores (e.g. `"Dreamwiseagency, store 2"`).
     - Added `shops` structured list: `[{"id": 2, "name": "Dreamwiseagency"}, {"id": 3, "name": "store 2"}]`.
     - Added `store_ids` integer array: `[2, 3]`.
   - **`/api/user/shops`**:
     - Added cashier domain filter: `[('id', 'in', user.store_ids.ids)]` when `user.havano_role == 'user'`.
     - Returns `default_pricelist_id`, `default_pricelist_name`, `pricelist_ids`, and `pricelist_names` for each shop.
   - **`/api/method/havano_pos_integration.api.get_products`**:
     - Includes all `advanced_price_ids` lines with `priceName`, `store`, `uom`, and `qty_to_be_sold`.

3. **`security/access_rights.xml` & `security/ir.model.access.csv`**:
   - Added read permissions for `base.group_user` on `ir.module.module` to resolve Odoo 19 Tenant Admin login access errors.

4. **Database Schema**:
   - Added `is_trial` boolean column to `havanoposdesk_subscription_plan` and `havanoposdesk_tenant`.
