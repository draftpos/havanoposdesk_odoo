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
        
        return result
