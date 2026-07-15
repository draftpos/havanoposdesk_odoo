-- =============================================================================
-- Havano POS Desk - Store Rename Cascade Script
-- =============================================================================
-- PURPOSE:
--   When a store is renamed, ALL historical records that stored the store name
--   as a denormalized text column will still show the OLD name. This script
--   updates every affected table so they all reference the NEW store name.
--
-- HOW TO USE:
--   1. Replace OLD_STORE_NAME and NEW_STORE_NAME below with the actual values.
--   2. Set TENANT_ID to the correct integer tenant ID.
--   3. Run AFTER renaming the store in the Havano admin UI.
--   4. Restart/reload Odoo so computed fields are recalculated.
--
-- TABLES UPDATED:
--   - havanoposdesk_sale                (store Char)
--   - havanoposdesk_stock_valuation     (store Char + store_id FK refix)
--   - havanoposdesk_stock_ledger        (store Char + store_id FK refix)
--   - havanoposdesk_stock_entry         (from_warehouse / to_warehouse Char)
--   - havanoposdesk_stock_entry_line    (store Char)
--   - havanoposdesk_stock_adjustment_line (store Char)
--   - havanoposdesk_purchase_line       (store Char)
-- =============================================================================

-- ===========================
-- CONFIGURE BEFORE RUNNING
-- ===========================
DO $$
DECLARE
    v_old_name   TEXT := 'My Old Shop Name';   -- <-- Change this
    v_new_name   TEXT := 'My New Shop Name';   -- <-- Change this
    v_tenant_id  INT  := 1;                    -- <-- Change this (your tenant ID)
    v_store_id   INT;
    v_count      INT;
BEGIN

    -- Safety check: verify the new name exists in the store table
    SELECT id INTO v_store_id
    FROM havanoposdesk_store
    WHERE name = v_new_name AND tenant_id = v_tenant_id
    LIMIT 1;

    IF v_store_id IS NULL THEN
        RAISE EXCEPTION
            'Store "%" not found in havanoposdesk_store for tenant_id=%. '
            'Make sure you have already saved the new store name in the UI.',
            v_new_name, v_tenant_id;
    END IF;

    RAISE NOTICE '=== Havano Store Rename Cascade ===';
    RAISE NOTICE 'OLD NAME : %', v_old_name;
    RAISE NOTICE 'NEW NAME : %', v_new_name;
    RAISE NOTICE 'TENANT   : %', v_tenant_id;
    RAISE NOTICE 'STORE_ID : %', v_store_id;
    RAISE NOTICE '====================================';

    -- ------------------------------------------------------------------
    -- 1. havanoposdesk_sale (store Char)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_sale
       SET store = v_new_name
     WHERE store = v_old_name AND tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[1] havanoposdesk_sale: % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 2. havanoposdesk_stock_valuation (store Char + store_id FK)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_stock_valuation
       SET store    = v_new_name,
           store_id = v_store_id
     WHERE store = v_old_name AND tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[2] havanoposdesk_stock_valuation: % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 3. havanoposdesk_stock_ledger (store Char + store_id FK)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_stock_ledger
       SET store    = v_new_name,
           store_id = v_store_id
     WHERE store = v_old_name AND tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[3] havanoposdesk_stock_ledger: % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 4. havanoposdesk_stock_entry (from_warehouse Char)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_stock_entry
       SET from_warehouse = v_new_name
     WHERE from_warehouse = v_old_name AND tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[4a] havanoposdesk_stock_entry (from_warehouse): % rows updated', v_count;

    -- 4b. havanoposdesk_stock_entry (to_warehouse Char)
    UPDATE havanoposdesk_stock_entry
       SET to_warehouse = v_new_name
     WHERE to_warehouse = v_old_name AND tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[4b] havanoposdesk_stock_entry (to_warehouse): % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 5. havanoposdesk_stock_entry_line (store Char if stored)
    --    Scope via parent stock_entry's tenant_id
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_stock_entry_line sl
       SET store = v_new_name
      FROM havanoposdesk_stock_entry se
     WHERE sl.stock_entry_id = se.id
       AND sl.store = v_old_name
       AND se.tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[5] havanoposdesk_stock_entry_line: % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 6. havanoposdesk_stock_adjustment_line (store Char if stored)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_stock_adjustment_line sal
       SET store = v_new_name
      FROM havanoposdesk_stock_adjustment sa
     WHERE sal.adjustment_id = sa.id
       AND sal.store = v_old_name
       AND sa.tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[6] havanoposdesk_stock_adjustment_line: % rows updated', v_count;

    -- ------------------------------------------------------------------
    -- 7. havanoposdesk_purchase_line (store Char if stored)
    -- ------------------------------------------------------------------
    UPDATE havanoposdesk_purchase_line pl
       SET store = v_new_name
      FROM havanoposdesk_purchase p
     WHERE pl.purchase_id = p.id
       AND pl.store = v_old_name
       AND p.tenant_id = v_tenant_id;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RAISE NOTICE '[7] havanoposdesk_purchase_line: % rows updated', v_count;

    RAISE NOTICE '=== Cascade complete. OLD="%" -> NEW="%" ===', v_old_name, v_new_name;

END $$;
