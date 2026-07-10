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
            
        if ' ' in email:
            raise UserError(_("Email cannot contain spaces."))
            
        if email.count('@') != 1:
            raise UserError(_("Email must contain exactly one @ symbol."))
            
        domain = email.split('@')[1]
        if '.' not in domain:
            raise UserError(_("Email domain must contain a dot (e.g., .com)."))
            
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
