from odoo import http
from odoo.http import request
import json

class HavanoPOSDeskAPI(http.Controller):

    # AUTHENTICATION
    @http.route('/api/auth/login', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_login(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
        
        db = data.get('db') or request.db or 'odoo_db_com'
        login = data.get('username') or data.get('login')
        password = data.get('password')
        
        if not login or not password:
            return request.make_response(json.dumps({'error': 'Username and password are required'}), headers=[('Content-Type', 'application/json')], status=400)
            
        from contextlib import ExitStack
        import odoo

        try:
            with ExitStack() as stack:
                if not request.db or request.db != db:
                    cr = stack.enter_context(odoo.modules.registry.Registry(db).cursor())
                    env = odoo.api.Environment(cr, None, {})
                else:
                    env = request.env
                    
                credential = {'login': login, 'password': password, 'type': 'password'}
                auth_info = request.session.authenticate(env, credential)
                uid = auth_info.get('uid') if isinstance(auth_info, dict) else request.session.uid
                
                request.session.db = db
                request.session.can_save = True
                request._save_session(env)
        except Exception as e:
            return request.make_response(json.dumps({'error': 'Authentication failed', 'message': str(e)}), headers=[('Content-Type', 'application/json')], status=401)
            
        if not uid:
            return request.make_response(json.dumps({'error': 'Authentication failed'}), headers=[('Content-Type', 'application/json')], status=401)
            
        user = request.env['res.users'].sudo().browse(uid)
        
        # Determine stores list based on role
        if user.havano_role == 'super_admin':
            stores = request.env['havanoposdesk.store'].sudo().search([])
        elif user.havano_role == 'admin':
            stores = request.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', user.tenant_id.id)]) if user.tenant_id else []
        else:
            stores = user.store_ids
            
        res_data = {
            'success': True,
            'session_id': request.session.sid,
            'user': {
                'id': user.id,
                'name': user.name,
                'role': user.havano_role,
                'tenant': {
                    'id': user.tenant_id.id,
                    'name': user.tenant_id.name,
                    'subscription_state': user.tenant_id.subscription_state,
                    'subscription_end_date': str(user.tenant_id.subscription_end_date) if user.tenant_id.subscription_end_date else None,
                    'plan_name': user.tenant_id.subscription_plan_id.name if user.tenant_id.subscription_plan_id else None,
                } if user.tenant_id else None,
                'default_store': {
                    'id': user.default_store_id.id,
                    'name': user.default_store_id.name
                } if user.default_store_id else None,
                'stores': [{'id': s.id, 'name': s.name} for s in stores]
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # PRODUCTS
    @http.route('/api/products/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_products(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        user = request.env['res.users'].sudo().browse(uid)
        
        if request.httprequest.method == 'GET':
            domain = []
            if user.havano_role != 'super_admin':
                if not user.tenant_id:
                    return request.make_response(json.dumps([]), headers=[('Content-Type', 'application/json')])
                domain.append(('tenant_id', '=', user.tenant_id.id))
                if user.havano_role == 'user':
                    domain.append(('store_id', 'in', user.store_ids.ids))
                    
            products = request.env['havanoposdesk.product'].sudo().search(domain)
            data = []
            for p in products:
                data.append({
                    'id': p.id,
                    'name': p.name,
                    'item_code': p.item_code,
                    'buying_price': p.buying_price,
                    'selling_price': p.selling_price,
                    'color_hex': p.color_hex,
                    'image_url': f'/web/image/havanoposdesk.product/{p.id}/image_1920',
                    'track_qty': p.track_qty,
                    'category': p.category_id.id if p.category_id else None,
                    'uom': p.uom_id.id if p.uom_id else None,
                    'tenant_id': p.tenant_id.id,
                    'store_id': p.store_id.id if p.store_id else None,
                })
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
            if user.havano_role != 'super_admin' and not user.tenant_id:
                return request.make_response(json.dumps({'error': 'User has no tenant assigned'}), headers=[('Content-Type', 'application/json')], status=400)
                
            tenant_id = user.tenant_id.id if user.havano_role != 'super_admin' else data.get('tenant_id')
            if not tenant_id:
                tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
                if not tenant:
                    tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                tenant_id = tenant.id
                
            store_id = data.get('store_id')
            if user.havano_role == 'user':
                if store_id and store_id not in user.store_ids.ids:
                    return request.make_response(json.dumps({'error': 'Unauthorized store access'}), headers=[('Content-Type', 'application/json')], status=403)
                store_id = store_id or user.default_store_id.id
                if not store_id and user.store_ids:
                    store_id = user.store_ids[0].id
            elif user.havano_role == 'admin':
                if store_id:
                    store = request.env['havanoposdesk.store'].sudo().browse(store_id)
                    if store.tenant_id.id != tenant_id:
                        return request.make_response(json.dumps({'error': 'Store does not belong to this tenant'}), headers=[('Content-Type', 'application/json')], status=403)
                else:
                    first_store = request.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
                    if not first_store:
                        first_store = request.env['havanoposdesk.store'].sudo().create({'name': 'Default Store', 'tenant_id': tenant_id})
                    store_id = first_store.id
            else: # super_admin
                if not store_id:
                    first_store = request.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', tenant_id)], limit=1)
                    if not first_store:
                        first_store = request.env['havanoposdesk.store'].sudo().create({'name': 'Default Store', 'tenant_id': tenant_id})
                    store_id = first_store.id
                    
            vals = {
                'name': data.get('name'),
                'item_code': data.get('item_code') or 'New',
                'buying_price': data.get('buying_price', 0.0),
                'selling_price': data.get('selling_price', 0.0),
                'color_hex': data.get('color_hex'),
                'track_qty': data.get('track_qty', True),
                'tenant_id': tenant_id,
                'store_id': store_id,
            }
            if data.get('category'):
                vals['category_id'] = data['category']
            if data.get('uom'):
                vals['uom_id'] = data['uom']
                
            product = request.env['havanoposdesk.product'].sudo().create(vals)
            
            res_data = {
                'id': product.id,
                'name': product.name,
                'item_code': product.item_code,
                'buying_price': product.buying_price,
                'selling_price': product.selling_price,
                'color_hex': product.color_hex,
                'image_url': f'/web/image/havanoposdesk.product/{product.id}/image_1920',
                'track_qty': product.track_qty,
                'category': product.category_id.id if product.category_id else None,
                'uom': product.uom_id.id if product.uom_id else None,
                'tenant_id': product.tenant_id.id,
                'store_id': product.store_id.id,
            }
            return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')], status=201)

    # CATEGORIES
    @http.route('/api/categories/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_categories(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        user = request.env['res.users'].sudo().browse(uid)
        
        if request.httprequest.method == 'GET':
            domain = []
            if user.havano_role != 'super_admin':
                if not user.tenant_id:
                    return request.make_response(json.dumps([]), headers=[('Content-Type', 'application/json')])
                domain.append(('tenant_id', '=', user.tenant_id.id))
            categories = request.env['havanoposdesk.category'].sudo().search(domain)
            data = [{'id': c.id, 'name': c.name, 'tenant_id': c.tenant_id.id} for c in categories]
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
            if user.havano_role != 'super_admin' and not user.tenant_id:
                return request.make_response(json.dumps({'error': 'User has no tenant assigned'}), headers=[('Content-Type', 'application/json')], status=400)
                
            tenant_id = user.tenant_id.id if user.havano_role != 'super_admin' else data.get('tenant_id')
            if not tenant_id:
                tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
                if not tenant:
                    tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                tenant_id = tenant.id
                
            cat = request.env['havanoposdesk.category'].sudo().create({
                'name': data.get('name'),
                'tenant_id': tenant_id,
            })
            return request.make_response(json.dumps({'id': cat.id, 'name': cat.name, 'tenant_id': cat.tenant_id.id}), headers=[('Content-Type', 'application/json')], status=201)

    # UOMS
    @http.route('/api/uoms/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_uoms(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        user = request.env['res.users'].sudo().browse(uid)
        
        if request.httprequest.method == 'GET':
            domain = []
            if user.havano_role != 'super_admin':
                if not user.tenant_id:
                    return request.make_response(json.dumps([]), headers=[('Content-Type', 'application/json')])
                domain.append(('tenant_id', '=', user.tenant_id.id))
            uoms = request.env['havanoposdesk.uom'].sudo().search(domain)
            data = [{'id': u.id, 'name': u.name, 'abbreviation': u.abbreviation, 'tenant_id': u.tenant_id.id} for u in uoms]
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
            if user.havano_role != 'super_admin' and not user.tenant_id:
                return request.make_response(json.dumps({'error': 'User has no tenant assigned'}), headers=[('Content-Type', 'application/json')], status=400)
                
            tenant_id = user.tenant_id.id if user.havano_role != 'super_admin' else data.get('tenant_id')
            if not tenant_id:
                tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
                if not tenant:
                    tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                tenant_id = tenant.id
                
            uom = request.env['havanoposdesk.uom'].sudo().create({
                'name': data.get('name'),
                'abbreviation': data.get('abbreviation'),
                'tenant_id': tenant_id,
            })
            return request.make_response(json.dumps({'id': uom.id, 'name': uom.name, 'abbreviation': uom.abbreviation, 'tenant_id': uom.tenant_id.id}), headers=[('Content-Type', 'application/json')], status=201)

    # SUBSCRIPTIONS & PAYMENTS
    @http.route('/api/subscription/plans', auth='public', methods=['GET'], type='http', csrf=False, cors='*')
    def get_subscription_plans(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        plans = request.env['havanoposdesk.subscription.plan'].sudo().search([])
        data = []
        for p in plans:
            data.append({
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'duration_days': p.duration_days,
                'max_stores': p.max_stores,
                'max_users': p.max_users,
                'max_terminals': p.max_terminals,
            })
        return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])

    @http.route('/api/subscription/status', auth='public', methods=['GET'], type='http', csrf=False, cors='*')
    def get_subscription_status(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        user = request.env['res.users'].sudo().browse(uid)
        tenant = user.tenant_id
        if not tenant:
            return request.make_response(json.dumps({'error': 'User has no tenant'}), headers=[('Content-Type', 'application/json')], status=400)
            
        # Count current usage
        stores_count = request.env['havanoposdesk.store'].sudo().search_count([('tenant_id', '=', tenant.id)])
        terminals_count = request.env['havanoposdesk.pos.terminal'].sudo().search_count([('tenant_id', '=', tenant.id)])
        cashiers_count = request.env['res.users'].sudo().search_count([('tenant_id', '=', tenant.id), ('havano_role', '=', 'user')])
        
        plan = tenant.subscription_plan_id
        res_data = {
            'tenant_id': tenant.id,
            'tenant_name': tenant.name,
            'subscription_state': tenant.subscription_state,
            'subscription_start_date': str(tenant.subscription_start_date) if tenant.subscription_start_date else None,
            'subscription_end_date': str(tenant.subscription_end_date) if tenant.subscription_end_date else None,
            'payment_status': tenant.payment_status,
            'plan': {
                'id': plan.id,
                'name': plan.name,
                'price': plan.price,
                'duration_days': plan.duration_days,
                'max_stores': plan.max_stores,
                'max_users': plan.max_users,
                'max_terminals': plan.max_terminals,
            } if plan else None,
            'usage': {
                'stores': {
                    'current': stores_count,
                    'limit': plan.max_stores if plan else 0
                },
                'terminals': {
                    'current': terminals_count,
                    'limit': plan.max_terminals if plan else 0
                },
                'cashiers': {
                    'current': cashiers_count,
                    'limit': plan.max_users if plan else 0
                }
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])

    @http.route('/api/subscription/subscribe', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def subscribe_plan(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        plan_id = data.get('plan_id')
        if not plan_id:
            return request.make_response(json.dumps({'error': 'plan_id is required'}), headers=[('Content-Type', 'application/json')], status=400)
            
        user = request.env['res.users'].sudo().browse(uid)
        tenant = user.tenant_id
        if not tenant:
            return request.make_response(json.dumps({'error': 'User has no tenant'}), headers=[('Content-Type', 'application/json')], status=400)
            
        plan = request.env['havanoposdesk.subscription.plan'].sudo().browse(plan_id)
        if not plan.exists():
            return request.make_response(json.dumps({'error': 'Plan not found'}), headers=[('Content-Type', 'application/json')], status=404)
            
        tenant.action_select_plan(plan.id)
        
        return request.make_response(json.dumps({
            'success': True,
            'message': f'Subscription to plan {plan.name} is pending payment.',
            'amount': plan.price,
            'state': tenant.subscription_state,
        }), headers=[('Content-Type', 'application/json')])

    @http.route('/api/subscription/pay', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def pay_subscription(self, **kw):
        uid = request.session.uid
        if not uid:
            return request.make_response(json.dumps({'error': 'Unauthorized'}), headers=[('Content-Type', 'application/json')], status=401)
            
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        user = request.env['res.users'].sudo().browse(uid)
        tenant = user.tenant_id
        if not tenant:
            return request.make_response(json.dumps({'error': 'User has no tenant'}), headers=[('Content-Type', 'application/json')], status=400)
            
        plan = tenant.subscription_plan_id
        if not plan:
            return request.make_response(json.dumps({'error': 'No plan selected to pay for'}), headers=[('Content-Type', 'application/json')], status=400)
            
        amount = data.get('amount', plan.price)
        payment_method = data.get('payment_method', 'in_app')
        
        if payment_method not in ['in_app', 'ecocash', 'paynow']:
            return request.make_response(json.dumps({'error': f'Unsupported payment method: {payment_method}'}), headers=[('Content-Type', 'application/json')], status=400)
            
        if payment_method == 'in_app':
            transaction_reference = data.get('transaction_reference', 'REF-MOCK')
            # Create payment record
            payment = request.env['havanoposdesk.subscription.payment'].sudo().create({
                'tenant_id': tenant.id,
                'subscription_plan_id': plan.id,
                'amount': amount,
                'payment_method': payment_method,
                'transaction_reference': transaction_reference,
                'state': 'done',
            })
            
            # Activate subscription
            tenant.action_pay_and_activate()
            
            return request.make_response(json.dumps({
                'success': True,
                'payment_id': payment.id,
                'subscription_state': tenant.subscription_state,
                'subscription_end_date': str(tenant.subscription_end_date),
            }), headers=[('Content-Type', 'application/json')])

        # Real payment processing (ecocash or paynow card redirection)
        provider = request.env['payment.provider'].sudo().search([('code', '=', 'havano_payments')], limit=1)
        if not provider:
            return request.make_response(json.dumps({'error': 'Havano Payments provider is not configured. Please configure it in SaaS Config.'}), headers=[('Content-Type', 'application/json')], status=400)

        import datetime
        import time
        reference = f"SUB-{tenant.id}-{plan.id}-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"

        payment = request.env['havanoposdesk.subscription.payment'].sudo().create({
            'tenant_id': tenant.id,
            'subscription_plan_id': plan.id,
            'amount': amount,
            'payment_method': payment_method,
            'transaction_reference': reference,
            'state': 'pending',
        })

        payment_method_rec = request.env['payment.method'].sudo().search([('code', '=', payment_method)], limit=1)

        tx = request.env['payment.transaction'].sudo().create({
            'provider_id': provider.id,
            'payment_method_id': payment_method_rec.id if payment_method_rec else False,
            'amount': amount,
            'currency_id': request.env.company.currency_id.id or request.env['res.currency'].sudo().search([('name', '=', 'USD')], limit=1).id,
            'reference': reference,
            'partner_id': user.partner_id.id,
            'operation': 'online_redirect',
            'subscription_payment_id': payment.id,
        })

        from odoo.addons.havano_payments.models.paynow_client import PaynowClient
        base_url = provider.get_base_url()
        result_url = f"{base_url}/payment/havano_payments/webhook?reference={reference}"

        if payment_method == 'ecocash':
            phone = data.get('phone')
            if not phone:
                tx._set_error('Phone number is missing for EcoCash')
                return request.make_response(json.dumps({'error': 'Phone number is required for EcoCash.'}), headers=[('Content-Type', 'application/json')], status=400)
                
            client = PaynowClient(provider.paynow_integration_id, provider.paynow_integration_key)
            mobile_res = client.initiate_mobile_transaction(
                reference=reference,
                amount=amount,
                authemail=user.email or "customer@example.com",
                phone=phone,
                method="ecocash",
                result_url=result_url,
                additional_info=f"Subscription for {tenant.name}"
            )
            if not mobile_res.get('success'):
                tx._set_error(mobile_res.get('error'))
                return request.make_response(json.dumps({'error': f"EcoCash initiation failed: {mobile_res.get('error')}"}), headers=[('Content-Type', 'application/json')], status=400)
            
            tx.paynow_poll_url = mobile_res['pollurl']
            tx._set_pending()
            
            return request.make_response(json.dumps({
                'success': True,
                'payment_id': payment.id,
                'state': 'pending',
                'instructions': mobile_res.get('instructions') or 'A prompt was sent to your phone. Please enter your PIN to complete the payment.',
                'poll_url': mobile_res['pollurl'],
                'reference': reference
            }), headers=[('Content-Type', 'application/json')])

        else: # paynow card redirection
            return_url = f"{base_url}/payment/havano_payments/return?reference={reference}"
            client = PaynowClient(provider.paynow_integration_id, provider.paynow_integration_key)
            init_res = client.initiate_transaction(
                reference=reference,
                amount=amount,
                authemail=user.email or "customer@example.com",
                return_url=return_url,
                result_url=result_url,
                additional_info=f"Subscription for {tenant.name}"
            )
            if not init_res.get('success'):
                tx._set_error(init_res.get('error'))
                return request.make_response(json.dumps({'error': f"Paynow initiation failed: {init_res.get('error')}"}), headers=[('Content-Type', 'application/json')], status=400)
            
            tx.paynow_poll_url = init_res['pollurl']
            tx._set_pending()
            
            return request.make_response(json.dumps({
                'success': True,
                'payment_id': payment.id,
                'state': 'pending',
                'redirect_url': init_res['browserurl'],
                'poll_url': init_res['pollurl'],
                'reference': reference
            }), headers=[('Content-Type', 'application/json')])


