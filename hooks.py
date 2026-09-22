"""
Post-install / post-migration hook to create performance composite indexes
on the havanoposdesk module tables. These indexes are additive-only and
do not affect any business logic, data integrity, or security rules.

Indexes created:
  - havanoposdesk_sale(tenant_id, state)
  - havanoposdesk_purchase(tenant_id, state)
  - havanoposdesk_stock_adjustment(tenant_id, state)
  - havanoposdesk_stock_entry(tenant_id, state)
  - havanoposdesk_stock_transfer(tenant_id, state)
  - havanoposdesk_production_order(tenant_id, state)
"""


def create_performance_indexes(cr):
    """Create composite B-Tree indexes for sub-millisecond tenant+state queries."""
    indexes = [
        ("havanoposdesk_sale",             "idx_comp_sale_tenant_state",             "tenant_id, state"),
        ("havanoposdesk_purchase",         "idx_comp_purchase_tenant_state",         "tenant_id, state"),
        ("havanoposdesk_stock_adjustment", "idx_comp_stock_adj_tenant_state",        "tenant_id, state"),
        ("havanoposdesk_stock_entry",      "idx_comp_stock_entry_tenant_state",      "tenant_id, state"),
        ("havanoposdesk_stock_transfer",   "idx_comp_stock_transfer_tenant_state",   "tenant_id, state"),
        ("havanoposdesk_production_order", "idx_comp_production_order_tenant_state", "tenant_id, state"),
    ]
    for table, idx_name, cols in indexes:
        cr.execute(
            f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table} ({cols});"
        )


def post_init_hook(env):
    """Called after module installation — creates composite performance indexes."""
    create_performance_indexes(env.cr)


def post_migrate_hook(env, version):
    """Called after every module upgrade — ensures indexes exist after schema changes."""
    create_performance_indexes(env.cr)
