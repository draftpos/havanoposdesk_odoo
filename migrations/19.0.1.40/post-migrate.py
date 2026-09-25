"""
Migration 19.0.1.40:
Fix cross-tenant sale, line, and payment leaks by:
1. Backfilling store_id on sales where store string is populated but store_id is NULL
2. Re-aligning havanoposdesk_sale.tenant_id with store.tenant_id
3. Re-aligning havanoposdesk_payment.tenant_id with sale.tenant_id
4. Re-aligning havanoposdesk_sale_line.tenant_id with sale.tenant_id
"""
import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("=== [HAVANO MIGRATION 19.0.1.40] Repairing cross-tenant sales & store isolation ===")

    # 1. Backfill missing store_id from store name within the same tenant
    cr.execute("""
        UPDATE havanoposdesk_sale s
        SET store_id = st.id
        FROM havanoposdesk_store st
        WHERE s.store_id IS NULL
          AND s.store IS NOT NULL
          AND s.store != ''
          AND s.tenant_id = st.tenant_id
          AND s.store = st.name;
    """)
    _logger.info("Backfilled store_id for %s sales", cr.rowcount)

    # 2. Fix sales where sale.tenant_id != store.tenant_id
    cr.execute("""
        UPDATE havanoposdesk_sale s
        SET tenant_id = st.tenant_id
        FROM havanoposdesk_store st
        WHERE s.store_id = st.id
          AND s.tenant_id != st.tenant_id;
    """)
    _logger.info("Re-aligned tenant_id for %s mismatched sales", cr.rowcount)

    # 3. Fix payments where payment.tenant_id != sale.tenant_id
    cr.execute("""
        UPDATE havanoposdesk_payment p
        SET tenant_id = s.tenant_id
        FROM havanoposdesk_sale s
        WHERE p.sale_id = s.id
          AND p.tenant_id != s.tenant_id;
    """)
    _logger.info("Re-aligned tenant_id for %s mismatched payments", cr.rowcount)

    # 4. Fix sale lines where sale_line.tenant_id != sale.tenant_id
    cr.execute("""
        UPDATE havanoposdesk_sale_line sl
        SET tenant_id = s.tenant_id
        FROM havanoposdesk_sale s
        WHERE sl.sale_id = s.id
          AND sl.tenant_id != s.tenant_id;
    """)
    _logger.info("Re-aligned tenant_id for %s mismatched sale lines", cr.rowcount)

    env = api.Environment(cr, SUPERUSER_ID, {})
    env.registry.clear_cache()
    _logger.info("=== [HAVANO MIGRATION 19.0.1.40] Completed Successfully ===")
