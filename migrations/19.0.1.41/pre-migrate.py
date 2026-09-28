"""
Migration 19.0.1.41 – pre-migrate

Backfill store_id on havanoposdesk_stock_ledger and havanoposdesk_stock_valuation
for rows that have a store name but a NULL store_id.

The security isolation rule for Stock Ledger filters by:
    ('tenant_id', '=', user.tenant_id.id)
and for 'user' role also by:
    ('store_id', 'in', user.store_ids.ids + [False])

Records with store_id = NULL fall into the [False] bucket and are still visible
to the user, which is acceptable (no store restriction).  However, older records
that *should* have a store_id resolved but don't would also slip through the
cross-tenant check if the tenant filter alone wasn't applied.  This migration
is a belt-and-braces fix to resolve as many NULL store_ids as possible using
the existing store name + tenant_id match.
"""


def migrate(cr, version):
    # Backfill Stock Ledger store_id
    cr.execute("""
        UPDATE havanoposdesk_stock_ledger sl
        SET store_id = s.id
        FROM havanoposdesk_store s
        WHERE sl.store IS NOT NULL
          AND sl.store != ''
          AND sl.store = s.name
          AND sl.tenant_id = s.tenant_id
          AND sl.store_id IS NULL
    """)
    ledger_count = cr.rowcount
    cr.execute("SELECT COUNT(*) FROM havanoposdesk_stock_ledger WHERE store_id IS NULL AND store IS NOT NULL AND store != ''")
    remaining_ledger = cr.fetchone()[0]

    # Backfill Stock Valuation store_id
    cr.execute("""
        UPDATE havanoposdesk_stock_valuation sv
        SET store_id = s.id
        FROM havanoposdesk_store s
        WHERE sv.store IS NOT NULL
          AND sv.store != ''
          AND sv.store = s.name
          AND sv.tenant_id = s.tenant_id
          AND sv.store_id IS NULL
    """)
    valuation_count = cr.rowcount

    import logging
    _logger = logging.getLogger(__name__)
    _logger.info(
        "Migration 19.0.1.41: Backfilled store_id on %d stock_ledger rows "
        "(%d still NULL after migration) and %d stock_valuation rows.",
        ledger_count, remaining_ledger, valuation_count,
    )
