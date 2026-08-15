from odoo import models
from odoo.http import request

_DB_COLUMNS_CHECKED = False

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    @classmethod
    def _dispatch(cls, endpoint):
        global _DB_COLUMNS_CHECKED
        if not _DB_COLUMNS_CHECKED and request and getattr(request, 'db', None):
            _DB_COLUMNS_CHECKED = True  # Ensure we only try this once per worker lifetime
            cr = request.env.cr
            try:
                # Check table existence first
                cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'havanoposdesk_tenant'")
                has_tenant = bool(cr.fetchone())
                cr.execute("SELECT 1 FROM information_schema.tables WHERE table_name = 'havanoposdesk_product_uom_price'")
                has_price = bool(cr.fetchone())
                
                if has_tenant:
                    cols = [
                        ("account_balance", "DOUBLE PRECISION DEFAULT 0.0"),
                        ("pending_subscription_plan_id", "INTEGER"),
                        ("pending_additional_terminals", "INTEGER DEFAULT 0"),
                        ("pending_additional_stores", "INTEGER DEFAULT 0"),
                        ("pending_subscription_total_amount", "DOUBLE PRECISION DEFAULT 0.0"),
                        ("additional_terminals", "INTEGER DEFAULT 0"),
                        ("additional_stores", "INTEGER DEFAULT 0"),
                        ("subscription_total_amount", "DOUBLE PRECISION DEFAULT 0.0"),
                        ("effective_max_stores", "INTEGER DEFAULT 0"),
                        ("effective_max_terminals", "INTEGER DEFAULT 0"),
                        ("allow_edit_item_code", "BOOLEAN DEFAULT FALSE"),
                        ("allow_negative_stock", "BOOLEAN DEFAULT TRUE"),
                        ("enable_tax", "BOOLEAN DEFAULT FALSE"),
                        ("enable_barcode", "BOOLEAN DEFAULT FALSE"),
                        ("enable_quotations", "BOOLEAN DEFAULT FALSE"),
                        ("enable_uom_conversion", "BOOLEAN DEFAULT FALSE"),
                        ("enable_payment_entries", "BOOLEAN DEFAULT FALSE"),
                        ("show_qty_on_hand", "BOOLEAN DEFAULT FALSE"),
                        ("enable_shift", "BOOLEAN DEFAULT FALSE"),
                        ("theme_color", "VARCHAR"),
                        ("product_name_format", "VARCHAR"),
                        ("restrict_price_modification", "BOOLEAN DEFAULT FALSE"),
                        ("payment_status", "VARCHAR"),
                    ]
                    # Fetch existing columns to avoid redundant ALTER TABLE calls (which require AccessExclusiveLocks)
                    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'havanoposdesk_tenant'")
                    existing_cols = {row[0] for row in cr.fetchall()}
                    
                    for col_name, col_type in cols:
                        if col_name not in existing_cols:
                            cr.execute(f"ALTER TABLE havanoposdesk_tenant ADD COLUMN {col_name} {col_type};")
                            
                if has_price:
                    cr.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'havanoposdesk_product_uom_price'")
                    existing_cols = {row[0] for row in cr.fetchall()}
                    if "initial_stock" not in existing_cols:
                        cr.execute("ALTER TABLE havanoposdesk_product_uom_price ADD COLUMN initial_stock DOUBLE PRECISION DEFAULT 0.0;")
            except Exception as e:
                import traceback
                import os
                try:
                    addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                    log_path = os.path.join(addon_dir, 'db_error.txt')
                    with open(log_path, 'w') as f:
                        f.write(traceback.format_exc())
                except Exception:
                    pass
                cr.rollback()
        return super()._dispatch(endpoint)

    @classmethod
    def _serve_fallback(cls):
        """
        Override to intercept /<configured_base>/* paths (e.g. /Havano/action-894)
        before the website module serves its 404 page.
        When the path starts with the configured web base URL, we serve the
        webclient SPA instead — the JS router handles the subpath client-side.
        """
        path = request.httprequest.path
        # Only act when a database is available
        if request.db:
            try:
                icp = request.env['ir.config_parameter'].sudo()
                configured_base = (icp.get_param('havanoposdesk.web_base_url') or 'Havano').lower()
                lower_path = path.lower()
                # Match /<base> or /<base>/<subpath>
                if lower_path == f'/{configured_base}' or lower_path.startswith(f'/{configured_base}/'):
                    from odoo.addons.web.controllers.home import Home  # type: ignore
                    response = Home().web_client()
                    if hasattr(response, 'flatten'):
                        response.flatten()
                    return response
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Error in fallback routing for %s: %s", path, e, exc_info=True)
        return super()._serve_fallback()

    def session_info(self):
        result = super(IrHttp, self).session_info()
        
        if request.env.user.has_group('base.group_user'):
            icp = request.env['ir.config_parameter'].sudo()
            result['havanoposdesk_app_name'] = icp.get_param('web.web_app_name', 'Havano')
            result['havanoposdesk_bot_name'] = icp.get_param('havanoposdesk.bot_name', 'HavanoBot')
            result['havanoposdesk_web_base_url'] = icp.get_param('havanoposdesk.web_base_url', 'Havano')
            
            # Override "My Company" in the Top Bar to show Store Name or Tenant Name
            user = request.env.user
            display_name = "My Company"
            if hasattr(user, 'default_store_id') and user.default_store_id:
                display_name = user.default_store_id.name
            elif hasattr(user, 'tenant_id') and user.tenant_id:
                display_name = user.tenant_id.name
                
            if 'user_companies' in result and 'current_company' in result['user_companies']:
                company_id = result['user_companies']['current_company']
                if 'allowed_companies' in result['user_companies'] and company_id in result['user_companies']['allowed_companies']:
                    result['user_companies']['allowed_companies'][company_id]['name'] = display_name
        
        return result
