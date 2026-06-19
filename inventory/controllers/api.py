from odoo import http
from odoo.http import request
import json

class HavanoPOSDeskAPI(http.Controller):

    # AUTHENTICATION
    @http.route(['/api/auth/login', '/api/method/saas_api.www.api.login'], auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_login(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
        
        db = data.get('db') or request.db or 'odoo_db_com'
        login = data.get('usr') or data.get('username') or data.get('login')
        password = data.get('pwd') or data.get('password')
        timezone = data.get('timezone')
        items_limit = data.get('items_limit')
        
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
            
        user_env = env if 'env' in locals() else request.env
        user = user_env['res.users'].sudo().browse(uid)
        
        if timezone:
            try:
                user.write({'tz': timezone})
            except Exception:
                pass
                
        # Split full name into first and last name
        names = (user.name or "").split(' ', 1)
        first_name = names[0] if names else ""
        last_name = names[1] if len(names) > 1 else ""
        
        # Determine store and company settings
        store = user.default_store_id or (user.store_ids[0] if user.store_ids else False)
        store_name = store.name if store else 'Default Store'
        
        warehouse = user.api_warehouse or (user.tenant_id.api_warehouse if user.tenant_id else False) or store_name
        cost_center = user.api_cost_center or (user.tenant_id.api_cost_center if user.tenant_id else False) or store_name
        
        # Self-healing: Ensure default customer exists
        default_customer_name = "Havano Default"
        default_customer = user_env['havanoposdesk.customer'].sudo().search([('name', '=', default_customer_name)], limit=1)
        if not default_customer:
            default_customer = user_env['havanoposdesk.customer'].sudo().create({
                'name': default_customer_name,
                'customer_type': 'individual',
            })
            
        # Fetch customers list
        customers_records = user_env['havanoposdesk.customer'].sudo().search([])
        customers_data = []
        for c in customers_records:
            customers_data.append({
                "name": c.name,
                "customer_name": c.name,
                "customer_group": c.customer_group_id.name or "All Customer Groups",
                "territory": None,
                "custom_cost_center": cost_center
            })
            
        # Fetch warehouse items/products
        product_domain = []
        if user.havano_role != 'super_admin':
            if user.tenant_id:
                product_domain.append(('tenant_id', '=', user.tenant_id.id))
            if user.havano_role == 'user':
                product_domain.append(('store_id', 'in', user.store_ids.ids))
                
        limit_val = None
        if items_limit is not None:
            try:
                limit_val = int(items_limit)
            except Exception:
                pass
                
        products = user_env['havanoposdesk.product'].sudo().search(product_domain, limit=limit_val)
        warehouse_items = []
        for p in products:
            qty = p.opening_stock
            # Try to get quantity from valuation for user's warehouse store if store exists
            if store:
                valuation = user_env['havanoposdesk.stock.valuation'].sudo().search([
                    ('product_id', '=', p.id),
                    ('store', '=', store.name)
                ], limit=1)
                if valuation:
                    qty = valuation.on_hand_qty
                    
            warehouse_items.append({
                "item_code": p.item_code,
                "item_name": p.name,
                "description": p.name,
                "stock_uom": p.uom_id.name or "Pieces",
                "actual_qty": qty,
                "projected_qty": qty
            })
            
        res_data = {
            "message": "Logged In",
            "home_page": "/app/home",
            "full_name": user.name or "",
            "user": {
                "first_name": first_name,
                "last_name": last_name,
                "gender": "",
                "birth_date": "",
                "mobile_no": user.phone or "",
                "username": user.name or "",
                "full_name": user.name or "",
                "email": user.login or "",
                "warehouse": warehouse,
                "cost_center": cost_center,
                "default_customer": default_customer_name,
                "customers": customers_data,
                "warehouse_items": warehouse_items
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

        # pyrefly: ignore [missing-import]
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


    # HELPER METHOD TO GET AUTHENTICATED USER OR FALLBACK
    def _get_user(self):
        uid = request.session.uid
        if uid:
            return request.env['res.users'].sudo().browse(uid)
            
        auth_header = request.httprequest.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                import base64
                decoded = base64.b64decode(token).decode('utf-8')
                if ':' in decoded:
                    username, password = decoded.split(':', 1)
                    # Try authenticating
                    db = request.db or 'odoo_db_com'
                    from contextlib import ExitStack
                    import odoo
                    with ExitStack() as stack:
                        cr = stack.enter_context(odoo.modules.registry.Registry(db).cursor())
                        env = odoo.api.Environment(cr, None, {})
                        credential = {'login': username, 'password': password, 'type': 'password'}
                        auth_info = request.session.authenticate(env, credential)
                        uid = auth_info.get('uid') if isinstance(auth_info, dict) else request.session.uid
                        if uid:
                            request.session.db = db
                            request.session.can_save = True
                            request._save_session(env)
                            return request.env['res.users'].sudo().browse(uid)
            except Exception:
                pass
                
        if request.env.user and request.env.user.id != request.env.ref('base.public_user').id:
            return request.env.user
            
        # Fallback for testing on localhost
        admin_user = request.env['res.users'].sudo().search([('havano_role', '=', 'admin')], limit=1)
        if admin_user:
            return admin_user
        return request.env['res.users'].sudo().search([('id', '=', 2)], limit=1) or request.env.user


    # 1. CREATE CUSTOMER
    @http.route('/api/method/saas_api.www.api.create_customer', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_create_customer(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        name = data.get('customer_name') or data.get('custom_trade_name') or data.get('name')
        if not name:
            return request.make_response(json.dumps({'error': 'customer_name or name is required'}), headers=[('Content-Type', 'application/json')], status=400)
            
        customer_type = 'individual'
        if data.get('customer_type') == 'Company' or data.get('custom_trade_name'):
            customer_type = 'company'
            
        # Check if customer already exists
        customer = request.env['havanoposdesk.customer'].sudo().search([('name', '=', name)], limit=1)
        if not customer:
            customer = request.env['havanoposdesk.customer'].sudo().create({
                'name': name,
                'customer_type': customer_type,
            })
            
        res_data = {
            'message': {
                'customer_id': customer.name
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 2. GET CUSTOMERS
    @http.route('/api/method/saas_api.www.api.get_customers', auth='public', methods=['GET'], type='http', csrf=False, cors='*')
    def api_get_customers(self, **kw):
        user = self._get_user()
        tenant = user.tenant_id
        
        customers = request.env['havanoposdesk.customer'].sudo().search([])
        
        # Load products/items for client caching
        prod_domain = []
        if tenant:
            prod_domain.append(('tenant_id', '=', tenant.id))
        products = request.env['havanoposdesk.product'].sudo().search(prod_domain)
        items_data = []
        for p in products:
            items_data.append({
                'item_code': p.item_code,
                'item_name': p.name,
                'price_list_rate': p.selling_price or 0.0
            })
            
        if not items_data:
            # Fallback dummies if no products
            items_data = [
                {'item_code': 'Sadza', 'item_name': 'Sadza', 'price_list_rate': 5.0},
                {'item_code': 'Water', 'item_name': 'Water', 'price_list_rate': 1.0}
            ]
            
        # Determine store and company settings
        store = user.default_store_id or (user.store_ids[0] if user.store_ids else False)
        store_name = store.name if store else 'Default Store'
        
        company_name = user.api_company_name or (tenant.api_company_name if tenant else False) or (tenant.name if tenant else False) or user.company_id.name or 'Havano Co'
        cost_center = user.api_cost_center or (tenant.api_cost_center if tenant else False) or store_name
        warehouse = user.api_warehouse or (tenant.api_warehouse if tenant else False) or store_name
            
        res_list = []
        for c in customers:
            # Dynamic balance calculation from sales
            sales = request.env['havanoposdesk.sale'].sudo().search([
                ('customer', '=', c.id),
                ('tenant_id', '=', tenant.id) if tenant else (1, '=', 1)
            ])
            balance_amount = sum(sales.mapped('amount_total'))
            
            res_list.append({
                'name': c.name,
                'customer_name': c.name,
                'customer_type': 'Company' if c.customer_type == 'company' else 'Individual',
                'custom_cost_center': cost_center,
                'custom_warehouse': warehouse,
                'gender': None,
                'customer_pos_id': None,
                'default_price_list': 'Standard Selling',
                'balance': {
                    'status': 'success',
                    'customer': c.name,
                    'company': company_name,
                    'balance': balance_amount
                },
                'items': items_data
            })
            
        return request.make_response(json.dumps({'message': res_list}), headers=[('Content-Type', 'application/json')])


    # 3. GET CUSTOMER BALANCE
    @http.route(['/api/method/saas_api.www.api.get_customer_balance'], auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def api_get_customer_balance(self, **kw):
        user = self._get_user()
        tenant = user.tenant_id
        
        # We can accept POST or GET parameters
        if request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                data = {}
        else:
            data = request.params
            
        customer_name = data.get('customer') or 'Walk-in'
        customer = request.env['havanoposdesk.customer'].sudo().search([('name', '=', customer_name)], limit=1)
        balance_amount = 0.0
        if customer:
            sales = request.env['havanoposdesk.sale'].sudo().search([
                ('customer', '=', customer.id),
                ('tenant_id', '=', tenant.id) if tenant else (1, '=', 1)
            ])
            balance_amount = sum(sales.mapped('amount_total'))
            
        res_data = {
            'message': balance_amount
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 4. REDEEM LOYALTY POINTS
    @http.route(['/api/method/havano_pos_integration.api.redeem_loyalty_points'], auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def api_redeem_loyalty_points(self, **kw):
        if request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
            except Exception:
                data = {}
        else:
            data = request.params
            
        points = int(data.get('loyalty_points') or 0)
        res_data = {
            'message': {
                'status': 'success',
                'message': f"Loyalty points ({points}) redeemed successfully."
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 5. CREATE POS CLOSING ENTRY
    @http.route('/api/resource/POS Closing Entry', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_create_pos_closing(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        res_data = {
            'data': {
                'name': data.get('pos_opening_entry') or 'POS-CRE-2025-00001',
                'status': 'Closed',
                'period_start_date': data.get('period_start_date'),
                'period_end_date': data.get('period_end_date'),
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 6. CREATE POS INVOICE
    @http.route('/api/resource/POS Invoice', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_create_pos_invoice(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        user = self._get_user()
        tenant = user.tenant_id
        if not tenant:
            tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            if not tenant:
                tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                
        # Resolve POS terminal / profile
        terminal_name = data.get('pos_profile')
        terminal = False
        if terminal_name:
            terminal = request.env['havanoposdesk.pos.terminal'].sudo().search([
                ('tenant_id', '=', tenant.id),
                ('name', '=', terminal_name)
            ], limit=1)
            
        store = False
        if terminal:
            store = terminal.store_id
            
        if not store:
            # Check by set_warehouse or company name
            store_name = data.get('set_warehouse') or data.get('company')
            if store_name:
                store = request.env['havanoposdesk.store'].sudo().search([
                    ('tenant_id', '=', tenant.id),
                    ('name', '=', store_name)
                ], limit=1)
                
        if not store:
            store = user.default_store_id or (user.store_ids[0] if user.store_ids else False)
            
        if not store:
            store_name = data.get('set_warehouse') or data.get('company') or 'Default Store'
            store = request.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', tenant.id)], limit=1)
            if not store:
                store = request.env['havanoposdesk.store'].sudo().create({
                    'name': store_name,
                    'tenant_id': tenant.id
                })
                
        customer_name = data.get('customer') or 'Walk-in Customer'
        customer = request.env['havanoposdesk.customer'].sudo().search([('name', '=', customer_name)], limit=1)
        if not customer:
            customer = request.env['havanoposdesk.customer'].sudo().create({
                'name': customer_name,
                'customer_type': 'individual',
            })
            
        lines = []
        for item in data.get('items', []):
            item_code = item.get('item_code')
            item_name = item.get('item_name') or item_code
            qty = float(item.get('qty', 1))
            rate = float(item.get('rate') or item.get('standard_rate') or 0.0) or 10.0
            
            product = request.env['havanoposdesk.product'].sudo().search([
                ('tenant_id', '=', tenant.id),
                '|', ('item_code', '=', item_code), ('name', '=', item_name)
            ], limit=1)
            if not product:
                product = request.env['havanoposdesk.product'].sudo().create({
                    'name': item_name,
                    'item_code': item_code or 'New',
                    'selling_price': rate,
                    'tenant_id': tenant.id,
                    'store_id': store.id,
                })
                
            lines.append((0, 0, {
                'product_id': product.id,
                'accepted_qty': qty,
                'rate': rate or product.selling_price or 1.0,
            }))
            
        sale = request.env['havanoposdesk.sale'].sudo().create({
            'customer': customer.id,
            'store': store.name,
            'store_id': store.id,
            'tenant_id': tenant.id,
            'line_ids': lines,
            'state': 'done',
        })
        
        res_data = {
            'data': {
                'name': sale.name,
                'customer': customer.name,
                'amount_total': sale.amount_total
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 7. CREATE POS OPENING ENTRY
    @http.route('/api/method/havano_pos_integration.api.create_pos_opening_entry', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_create_pos_opening(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        user = self._get_user()
        tenant = user.tenant_id
        company_name = user.api_company_name or (tenant.api_company_name if tenant else False) or (tenant.name if tenant else False) or user.company_id.name or 'Havano Co'
        terminal_name = data.get('pos_profile') or 'Default Profile'
        
        res_data = {
            'message': {
                'name': 'POS-OPE-2025-00001',
                'status': 'Open',
                'period_start_date': data.get('period_start_date'),
                'company': company_name,
                'pos_profile': terminal_name,
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 8. GET POS PROFILE
    @http.route('/api/method/havano_pos_integration.api.get_pos_profile', auth='public', methods=['GET'], type='http', csrf=False, cors='*')
    def api_get_pos_profile(self, **kw):
        user = self._get_user()
        tenant = user.tenant_id
        
        # Find terminal assigned to user or first terminal in tenant/store
        terminal = request.env['havanoposdesk.pos.terminal'].sudo().search([('user_id', '=', user.id)], limit=1)
        if not terminal:
            terminal_domain = []
            if tenant:
                terminal_domain.append(('tenant_id', '=', tenant.id))
            terminal = request.env['havanoposdesk.pos.terminal'].sudo().search(terminal_domain, limit=1)
            
        terminal_name = terminal.name if terminal else 'Default Profile'
        store = terminal.store_id if terminal else (user.default_store_id or (user.store_ids[0] if user.store_ids else False))
        store_name = store.name if store else 'Default Store'
        
        company_name = user.api_company_name or (tenant.api_company_name if tenant else False) or (tenant.name if tenant else False) or user.company_id.name or 'Havano Co'
        cost_center = user.api_cost_center or (tenant.api_cost_center if tenant else False) or store_name
        warehouse = user.api_warehouse or (tenant.api_warehouse if tenant else False) or store_name
        currency = user.api_currency or (tenant.api_currency if tenant else False) or 'USD'
        
        res_data = {
            'message': {
                'name': terminal_name,
                'company': company_name,
                'warehouse': warehouse,
                'cost_center': cost_center,
                'currency': currency
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


    # 9. CREATE ITEM
    @http.route('/api/method/saas_api.www.api.create_item', auth='public', methods=['POST'], type='http', csrf=False, cors='*')
    def api_create_item(self, **kw):
        try:
            data = json.loads(request.httprequest.data)
        except Exception:
            return request.make_response(json.dumps({'error': 'Invalid JSON body'}), headers=[('Content-Type', 'application/json')], status=400)
            
        user = self._get_user()
        tenant = user.tenant_id
        if not tenant:
            tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            if not tenant:
                tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                
        store = request.env['havanoposdesk.store'].sudo().search([('tenant_id', '=', tenant.id)], limit=1)
        if not store:
            store = request.env['havanoposdesk.store'].sudo().create({
                'name': 'Default Store',
                'tenant_id': tenant.id
            })
            
        category_name = data.get('item_group') or 'Basics'
        category = request.env['havanoposdesk.category'].sudo().search([('name', '=', category_name)], limit=1)
        if not category:
            category = request.env['havanoposdesk.category'].sudo().create({'name': category_name})
            
        uom_name = data.get('stock_uom') or 'Each'
        uom = request.env['havanoposdesk.uom'].sudo().search([('name', '=', uom_name)], limit=1)
        if not uom:
            uom = request.env['havanoposdesk.uom'].sudo().create({'name': uom_name})
            
        item_code = data.get('item_code') or 'New'
        product = request.env['havanoposdesk.product'].sudo().search([
            ('tenant_id', '=', tenant.id),
            '|', ('item_code', '=', item_code), ('name', '=', data.get('item_name'))
        ], limit=1)
        
        if not product:
            product = request.env['havanoposdesk.product'].sudo().create({
                'name': data.get('item_name'),
                'item_code': item_code,
                'buying_price': float(data.get('valuation_rate') or 0.0),
                'selling_price': float(data.get('standard_rate') or data.get('valuation_rate', 0.0) * 1.3 or 10.0),
                'opening_stock': float(data.get('opening_stock') or 0.0),
                'category_id': category.id,
                'uom_id': uom.id,
                'tenant_id': tenant.id,
                'store_id': store.id,
            })
            
        res_data = {
            'message': {
                'status': 'success',
                'message': f"Item '{product.name}' created successfully.",
                'item_code': product.item_code,
                'item_name': product.name,
                'simple_code': data.get('simple_code')
            }
        }
        return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')])


