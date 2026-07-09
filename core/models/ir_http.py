from odoo import models
from odoo.http import request

class IrHttp(models.AbstractModel):
    _inherit = 'ir.http'

    def session_info(self):
        result = super(IrHttp, self).session_info()
        
        if request.env.user.has_group('base.group_user'):
            icp = request.env['ir.config_parameter'].sudo()
            result['havanoposdesk_app_name'] = icp.get_param('web.web_app_name', 'Havano')
            result['havanoposdesk_bot_name'] = icp.get_param('havanoposdesk.bot_name', 'HavanoBot')
            result['havanoposdesk_web_base_url'] = icp.get_param('havanoposdesk.web_base_url', 'havano')
            
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
