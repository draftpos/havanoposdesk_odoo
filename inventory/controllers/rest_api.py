import json
import logging
from odoo import http, fields
from odoo.http import request
from .api import HavanoPOSDeskAPI

_logger = logging.getLogger(__name__)

class HavanoPOSDeskRESTAPI(HavanoPOSDeskAPI):

    MODEL_MAP = {
        'category': 'havanoposdesk.category',
        'stock_adjustment': 'havanoposdesk.stock.adjustment',
        'sale_invoice': 'havanoposdesk.sale',
        'purchase': 'havanoposdesk.purchase',
        'supplier': 'havanoposdesk.supplier',
        'customer': 'havanoposdesk.customer',
        'stock_transfer': 'havanoposdesk.stock.transfer',
        'credit_note': 'havanoposdesk.sale',
        'debit_note': 'havanoposdesk.purchase',
    }

    def _get_auth_env(self):
        token = request.httprequest.headers.get('Authorization')
        if not token:
            token = request.httprequest.args.get('token')
        
        uid, login = self._verify_token(token)
        if not uid:
            user = self._get_user()
            uid = user.id

        env, custom_cr = self._get_env(user_id=uid)
        return env, uid, custom_cr

    @http.route([
        '/api/<string:model_name>',
        '/api/<string:model_name>/<int:record_id>'
    ], auth='public', methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'], type='http', csrf=False, cors='*')
    def generic_rest_api(self, model_name, record_id=None, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)

        if model_name not in self.MODEL_MAP:
            return self._make_json_response({"error": f"Model {model_name} not supported via this API."}, status=404)

        odoo_model = self.MODEL_MAP[model_name]
        env, uid, custom_cr = self._get_auth_env()

        if not uid:
            if custom_cr: custom_cr.close()
            return self._make_json_response({"error": "Unauthorized"}, status=401)

        try:
            method = request.httprequest.method
            Model = env[odoo_model].sudo()
            
            # GET (Read)
            if method == 'GET':
                if record_id:
                    record = Model.browse(record_id)
                    if not record.exists():
                        return self._make_json_response({"error": "Record not found"}, status=404)
                    data = record.read()[0]
                    return self._make_json_response({"data": data})
                else:
                    domain = []
                    # Basic tenant isolation
                    user = env['res.users'].browse(uid)
                    if user.tenant_id and hasattr(Model, 'tenant_id'):
                        domain.append(('tenant_id', '=', user.tenant_id.id))
                    
                    records = Model.search(domain)
                    data = records.read()
                    return self._make_json_response({"data": data})

            # POST (Create)
            elif method == 'POST':
                params = self._get_request_json() or {}
                if not params:
                    params = request.httprequest.args.to_dict()
                
                # Auto-inject tenant
                user = env['res.users'].browse(uid)
                if user.tenant_id and hasattr(Model, 'tenant_id') and 'tenant_id' not in params:
                    params['tenant_id'] = user.tenant_id.id

                record = Model.create(params)
                return self._make_json_response({"message": "Created", "id": record.id, "data": record.read()[0]}, status=201)

            # PUT (Update)
            elif method == 'PUT':
                if not record_id:
                    return self._make_json_response({"error": "Record ID required for PUT"}, status=400)
                
                record = Model.browse(record_id)
                if not record.exists():
                    return self._make_json_response({"error": "Record not found"}, status=404)
                
                params = self._get_request_json() or {}
                if not params:
                    params = request.httprequest.args.to_dict()
                
                record.write(params)
                return self._make_json_response({"message": "Updated", "data": record.read()[0]})

            # DELETE
            elif method == 'DELETE':
                if not record_id:
                    return self._make_json_response({"error": "Record ID required for DELETE"}, status=400)
                
                record = Model.browse(record_id)
                if not record.exists():
                    return self._make_json_response({"error": "Record not found"}, status=404)
                
                record.unlink()
                return self._make_json_response({"message": "Deleted"})

        except Exception as e:
            _logger.exception(f"Error in generic REST API for {model_name}")
            return self._make_json_response({"error": str(e)}, status=500)
        finally:
            if custom_cr:
                custom_cr.close()

    @http.route('/api/signup', auth='public', methods=['POST', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_signup(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)

        params = self._get_request_json() or request.httprequest.args.to_dict()
        email = params.get('email')
        password = params.get('password')
        name = params.get('name') or params.get('full_name')
        
        if not email or not password or not name:
            return self._make_json_response({"error": "Missing required fields: email, password, name"}, status=400)

        import odoo
        db = request.session.db or 'odoo_db_com'
        registry = odoo.modules.registry.Registry(db)
        
        with registry.cursor() as cr:
            env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
            
            # Check if email exists
            if env['res.users'].search([('login', '=', email)]):
                return self._make_json_response({"error": "Email already in use"}, status=400)
            
            # Create Tenant
            tenant = env['havanoposdesk.tenant'].create({
                'name': f"{name}'s Tenant",
                'email': email,
                'allow_multi_currency': True,
                'allow_advanced_pricing': True
            })
            
            # Create Store
            store = env['havanoposdesk.store'].create({
                'name': 'Main Store',
                'tenant_id': tenant.id,
                'is_default': True
            })
            
            # Create User
            user = env['res.users'].create({
                'name': name,
                'login': email,
                'password': password,
                'tenant_id': tenant.id,
                'havano_role': 'admin',
                'store_ids': [(4, store.id)],
                'default_store_id': store.id
            })

            # Return defaults
            return self._make_json_response({
                "message": "Signup successful",
                "user_id": user.id,
                "tenant_id": tenant.id,
                "store_id": store.id
            }, status=201)

    @http.route('/api/credit_note', auth='public', methods=['POST', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_credit_note(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)
        
        params = self._get_request_json() or request.httprequest.args.to_dict()
        params['is_return'] = True
        
        request.httprequest.data = json.dumps(params).encode('utf-8')
        return self.generic_rest_api('sale_invoice', **kwargs)

    @http.route('/api/debit_note', auth='public', methods=['POST', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_debit_note(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)
        
        return self._make_json_response({"error": "Debit notes on sales are not currently supported; use purchase returns instead."}, status=400)
