from odoo import http, _
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.session import Session
from odoo.addons.web.controllers.webmanifest import WebManifest
import werkzeug
import logging

_logger = logging.getLogger(__name__)

class HavanoAccessController(http.Controller):
    @http.route('/havano/check_access', type='json', auth='user')
    def check_access(self, model):
        # Default allow if not matched
        res = {'canCreate': True, 'canViewDetail': True}
        
        from odoo.addons.havanoposdesk_odoo.core.models.user_rights import MODEL_FEATURE_MAP
        
        if model in MODEL_FEATURE_MAP:
            user = request.env.user
            if user.id == 1 or getattr(user, 'havano_role', None) == 'super_admin':
                return res
                
            profile = user.user_rights_profile_id
            if profile:
                feature_name = MODEL_FEATURE_MAP[model]
                bo_perm = profile.backoffice_permission_ids.filtered(lambda p: p.feature == feature_name)
                if bo_perm and bo_perm[0].is_read_only:
                    res['canCreate'] = False
                    res['canViewDetail'] = False
                    
        return res

class HavanoWebManifest(WebManifest):
    def _get_webmanifest(self):
        manifest = super()._get_webmanifest()
        
        icp = request.env['ir.config_parameter'].sudo()
        configured_base = (icp.get_param('havanoposdesk.web_base_url') or 'Havano')
        if not configured_base.startswith('/'):
            configured_base = '/' + configured_base
        if configured_base.lower() == '/havano':
            configured_base = '/Havano'
            
        manifest['start_url'] = f"{configured_base}"
        
        # Override the icons with the Havano logo
        manifest['icons'] = [{
            'src': '/havanoposdesk_odoo/static/description/icon.png',
            'sizes': '192x192',
            'type': 'image/png',
        }, {
            'src': '/havanoposdesk_odoo/static/description/icon.png',
            'sizes': '512x512',
            'type': 'image/png',
        }]
        
        return manifest

class HavanoAuthSignup(AuthSignupHome):

    def _login_redirect(self, uid, redirect=None):
        icp = request.env['ir.config_parameter'].sudo()
        configured_base = (icp.get_param('havanoposdesk.web_base_url') or 'Havano')
        
        # Format properly
        if not configured_base.startswith('/'):
            configured_base = '/' + configured_base
        return configured_base

    @http.route('/web/login', type='http', auth="none")
    def web_login(self, redirect=None, **kw):
        icp = request.env['ir.config_parameter'].sudo()
        configured_base = (icp.get_param('havanoposdesk.web_base_url') or 'Havano')
        if not configured_base.startswith('/'):
            configured_base = '/' + configured_base
        if configured_base.lower() == '/havano':
            configured_base = '/Havano'
            
        if redirect and '/odoo' in redirect:
            redirect = redirect.replace('/odoo', configured_base)
        elif not redirect:
            redirect = configured_base
            
        try:
            _logger.info(f"Havano web_login called. self is: {type(self)}. _login_redirect evaluates to: {self._login_redirect(request.session.uid, redirect=redirect)}")
        except Exception as e:
            _logger.info(f"Exception calling _login_redirect: {e}")

        return super(HavanoAuthSignup, self).web_login(redirect=redirect, **kw)

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False, captcha='signup')
    def web_auth_signup(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()

        if not qcontext.get('token') and not qcontext.get('signup_enabled'):
            raise werkzeug.exceptions.NotFound()

        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
                request.env = request.env(context=dict(request.env.context, no_reset_password=True, create_user=True))
                self.do_signup(qcontext)
                
                if request.session.uid is None:
                    public_user = request.env.ref('base.public_user')
                    request.update_env(user=public_user)

                # WE INTENTIONALLY SKIP SENDING THE SYNCHRONOUS 'WELCOME EMAIL' HERE
                # TO PREVENT A 10-15 SECOND SMTP BLOCKING DELAY!
                # Havano uses an async verification email instead.
                
                return self.web_login(*args, **kw)
            except Exception as e:
                _logger.exception("Error during signup")
                # Handle both native string exceptions and Odoo UserError/SignupError generically
                error_msg = getattr(e, 'args', [str(e)])[0]
                qcontext['error'] = _("Could not create a new account. ") + str(error_msg)

        elif 'signup_email' in qcontext:
            user = request.env['res.users'].sudo().search([('email', '=', qcontext.get('signup_email')), ('state', '!=', 'new')], limit=1)
            if user:
                return request.redirect('/web/login?login=%s&redirect=/web' % user.login)

        response = request.render('auth_signup.signup', qcontext)
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
        return response

    def get_auth_signup_qcontext(self):
        qcontext = super(HavanoAuthSignup, self).get_auth_signup_qcontext()
        qcontext['countries'] = request.env['res.country'].sudo().search([])
        qcontext['states'] = request.env['res.country.state'].sudo().search([])
        return qcontext

    def _prepare_signup_values(self, qcontext):
        values = super(HavanoAuthSignup, self)._prepare_signup_values(qcontext)
        import re
        from odoo.exceptions import UserError
        
        # 1. Password validation
        password = values.get('password')
        if password:
            if not re.match(r'^(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]).{8,}$', password):
                raise UserError(_("Password must be at least 8 characters long, contain 1 uppercase letter, 1 number, and 1 special character."))
        
        # 2. Name Validation (strictly letters and spaces)
        name = values.get('name')
        if name and not re.match(r'^[A-Za-z\s]+$', name):
            raise UserError(_("Full Name can only contain letters and spaces."))
            
        # 3. Email Validation
        email = values.get('login')
        if not email:
            raise UserError(_("Email is required."))
            
        if len(email) > 254:
            raise UserError(_("Email is too long."))
            
        if not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
            raise UserError(_("Please enter a valid email address (e.g. name@domain.com)."))
            
        domain = email.split('@')[1]
        tld = domain.split('.')[-1]
        if len(tld) < 2:
            raise UserError(_("Email top-level domain must be at least 2 letters."))
            
        # 4. Check if email already exists
        existing_user = request.env['res.users'].sudo().search([('login', '=', email)], limit=1)
        if existing_user:
            raise UserError(_("Email already in use. Please log in instead."))
            
        # Add custom fields
        if qcontext.get('organization_name'):
            values['organization_name'] = qcontext.get('organization_name')
        
        phone = qcontext.get('phone_number')
        country = qcontext.get('country_code', '')
        if phone:
            values['phone'] = f"{country}{phone}"
            
        return values

class HavanoSession(Session):
    @http.route('/web/session/logout', type='http', auth="none")
    def logout(self, redirect='/web/login'):
        # Force a clean redirect to login without carrying over ?redirect=/odoo
        return super(HavanoSession, self).logout(redirect='/web/login')

