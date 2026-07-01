from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from odoo.addons.web.controllers.webmanifest import WebManifest


class HavanoHome(Home):
    """
    White-label URL override: adds /havano (and /havano/<subpath>) routes
    that serve the same webclient as /odoo.
    Visiting / also redirects to /havano instead of /odoo.
    """

    @http.route(['/havano', '/havano/<path:subpath>'], type='http', auth='none',
                readonly=Home._web_client_readonly)
    def havano_client(self, s_action=None, **kw):
        return self.web_client(s_action=s_action, **kw)

    @http.route('/', type='http', auth='none')
    def index(self, s_action=None, db=None, **kw):
        """Redirect root to /havano instead of /odoo."""
        from odoo.addons.web.controllers.utils import is_user_internal
        if request.db and request.session.uid and not is_user_internal(request.session.uid):
            return request.redirect_query('/web/login_successful', query=request.params)
        return request.redirect_query('/havano', query=request.params)


class HavanoWebManifest(WebManifest):
    """
    Override the PWA web manifest to use Havano branding:
    - App name from ir.config_parameter 'web.web_app_name' (set in Settings)
    - scope and start_url use /havano instead of /odoo
    - theme_color from ir.config_parameter 'havanoposdesk.theme_color'
    - Havano icons instead of Odoo icons
    """

    def _get_webmanifest(self):
        icp = request.env['ir.config_parameter'].sudo()
        web_app_name = icp.get_param('web.web_app_name', 'Havano')
        theme_color = icp.get_param('havanoposdesk.theme_color', '#714B67')
        bg_color = icp.get_param('havanoposdesk.pwa_background_color', '#714B67')
        base_path = icp.get_param('havanoposdesk.web_base_url', 'havano')
        scope = f'/{base_path}'

        manifest = {
            'name': web_app_name,
            'short_name': web_app_name,
            'scope': scope,
            'start_url': scope,
            'display': 'standalone',
            'background_color': bg_color,
            'theme_color': theme_color,
            'prefer_related_applications': False,
        }

        # Icons
        small_icon = icp.get_param('havanoposdesk.pwa_small_icon', '/Havanoposdesk_odoo/static/src/img/havano-icon-192x192.png')
        large_icon = icp.get_param('havanoposdesk.pwa_large_icon', '/Havanoposdesk_odoo/static/src/img/havano-icon-512x512.png')
        
        manifest['icons'] = [
            {
                'src': small_icon,
                'sizes': '192x192',
                'type': 'image/png',
            },
            {
                'src': large_icon,
                'sizes': '512x512',
                'type': 'image/png',
            }
        ]

        manifest['shortcuts'] = self._get_shortcuts()
        return manifest

    @http.route(['/odoo/offline', '/havano/offline'], type='http', auth='public', methods=['GET'], readonly=True)
    def offline(self):
        """ Returns the offline page delivered by the service worker """
        icp = request.env['ir.config_parameter'].sudo()
        web_app_name = icp.get_param('web.web_app_name', 'Havano')
        return request.render('Havanoposdesk_odoo.havano_offline_page', {
            'app_name': web_app_name,
        })

    @http.route('/web/service-worker.js', type='http', auth='public', methods=['GET'], readonly=True)
    def service_worker(self):
        """Override service worker to use /havano scope."""
        icp = request.env['ir.config_parameter'].sudo()
        base_path = icp.get_param('havanoposdesk.web_base_url', 'havano')
        scope = f'/{base_path}'
        response = request.make_response(
            self._get_service_worker_content(),
            [
                ('Content-Type', 'text/javascript'),
                ('Service-Worker-Allowed', scope),
            ]
        )
        return response
