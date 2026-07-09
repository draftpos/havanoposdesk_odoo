from odoo import http, _
from odoo.http import request
from odoo.addons.auth_signup.controllers.main import AuthSignupHome
import werkzeug
import logging

_logger = logging.getLogger(__name__)

class HavanoAuthSignup(AuthSignupHome):

    @http.route('/web/signup', type='http', auth='public', website=True, sitemap=False, captcha='signup')
    def web_auth_signup(self, *args, **kw):
        qcontext = self.get_auth_signup_qcontext()

        if not qcontext.get('token') and not qcontext.get('signup_enabled'):
            raise werkzeug.exceptions.NotFound()

        if 'error' not in qcontext and request.httprequest.method == 'POST':
            try:
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
