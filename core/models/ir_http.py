from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

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
                    from odoo.addons.web.controllers.home import Home
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
