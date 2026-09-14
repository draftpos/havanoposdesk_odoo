"""
Migration 19.0.1.39:
Auto-expire all existing tenants whose subscription_end_date has passed (< CURRENT_DATE)
and whose subscription_state is not already 'expired' or 'cancelled'.
"""
import logging
from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info("=== [HAVANO MIGRATION 19.0.1.39] Auto-expiring passed subscriptions ===")

    cr.execute("""
        UPDATE havanoposdesk_tenant
        SET subscription_state = 'expired'
        WHERE subscription_end_date IS NOT NULL
          AND subscription_end_date < CURRENT_DATE
          AND subscription_state NOT IN ('expired', 'cancelled');
    """)
    _logger.info("Updated %s passed tenant subscriptions to 'expired'", cr.rowcount)

    env = api.Environment(cr, SUPERUSER_ID, {})
    env.registry.clear_cache()
    _logger.info("=== [HAVANO MIGRATION 19.0.1.39] Completed Successfully ===")
