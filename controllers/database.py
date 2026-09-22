# Part of Havanoposdesk. See LICENSE file for full copyright and licensing details.

import odoo
import odoo.modules.registry
from odoo import http
from odoo.http import dispatch_rpc, request
from odoo.tools.misc import str2bool
from odoo.tools.translate import _

from odoo.addons.web.controllers.database import Database as OdooDatabase

import logging
_logger = logging.getLogger(__name__)

DBNAME_PATTERN = r'^[a-zA-Z0-9][a-zA-Z0-9_.-]+$'


class HavanoDatabaseController(OdooDatabase):
    """
    Override the Odoo database manager routes to serve a branded Havano UI.
    All POST operations (create, backup, restore, duplicate, drop, change_password)
    are inherited as-is from the parent Database controller.
    """

    def _get_branding(self):
        """Fetch whitelabel settings from ir.config_parameter (best-effort)."""
        try:
            ICP = odoo.registry(http.db_list()[0])['ir.config_parameter']
            with odoo.registry(http.db_list()[0]).cursor() as cr:
                env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
                app_name = env['ir.config_parameter'].get_param('web.web_app_name', 'Havano')
                favicon = env['ir.config_parameter'].get_param(
                    'havanoposdesk.favicon',
                    '/havanoposdesk_odoo/static/src/img/favicon.png'
                )
                logo = env['ir.config_parameter'].get_param(
                    'havanoposdesk.logo',
                    '/havanoposdesk_odoo/static/src/img/havan_2.png'
                )
        except Exception:
            app_name = 'Havano'
            favicon = '/havanoposdesk_odoo/static/src/img/favicon.png'
            logo = '/havanoposdesk_odoo/static/src/img/havan_2.png'
        return {'app_name': app_name, 'favicon': favicon, 'logo': logo}

    def _havano_render(self, manage=True, error=None):
        """Render our custom branded database manager page."""
        branding = self._get_branding()

        insecure = odoo.tools.config.verify_admin_password('admin')
        list_db = odoo.tools.config['list_db']

        try:
            databases = http.db_list()
            incompatible_databases = odoo.service.db.list_db_incompatible(databases)
        except odoo.exceptions.AccessDenied:
            databases = [request.db] if request.db else []
            incompatible_databases = []

        langs = odoo.service.db.exp_list_lang()
        countries = odoo.service.db.exp_list_countries()

        values = {
            'manage': manage,
            'insecure': insecure,
            'list_db': list_db,
            'databases': databases,
            'incompatible_databases': incompatible_databases,
            'langs': langs,
            'countries': countries,
            'pattern': DBNAME_PATTERN,
            'error': error,
            **branding,
        }

        return request.render(
            'havanoposdesk_odoo.havano_database_manager',
            values,
            headers=[('Content-Type', 'text/html')]
        )

    @http.route('/web/database/manager', type='http', auth='none')
    def manager(self, **kw):
        if request.db:
            request.env.cr.close()
        return self._havano_render(manage=True)

    @http.route('/web/database/selector', type='http', auth='none')
    def selector(self, **kw):
        if request.db:
            request.env.cr.close()
        return self._havano_render(manage=False)
