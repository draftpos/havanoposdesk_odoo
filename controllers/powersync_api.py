# -*- coding: utf-8 -*-
"""
PowerSync Integration API for Havano POS (Odoo 19 Backend)
Provides:
1. JWT issuance for client authentication against the PowerSync service (/api/powersync/token)
2. Batch mutation endpoint for offline writes uploaded by the POS client (/api/powersync/upload)
   Supports: Sales with payments, Cashier Shifts (open/close), and Customer creations.
"""

import json
import logging
import time
import base64
import hashlib
import hmac
from odoo import http, fields, tools
from odoo.http import request

_logger = logging.getLogger(__name__)

DEFAULT_JWT_SECRET = "havano_powersync_super_secret_jwt_key_2026"
DEFAULT_POWERSYNC_URL = "http://127.0.0.1:8080"


def _b64url_encode(data_bytes):
    """Base64 URL-safe encode without padding."""
    if isinstance(data_bytes, str):
        data_bytes = data_bytes.encode('utf-8')
    return base64.urlsafe_b64encode(data_bytes).decode('utf-8').rstrip('=')


def generate_powersync_jwt(user_id, tenant_id, store_id=None, store_ids=None, role=None, secret_key=None, expires_in=2592000):
    """Generate a HS256 JWT for PowerSync client authentication."""
    secret = secret_key or DEFAULT_JWT_SECRET
    now = int(time.time())

    header = {
        "alg": "HS256",
        "typ": "JWT"
    }

    payload = {
        "sub": str(user_id),
        "iss": "havano_pos_odoo",
        "aud": "powersync",
        "iat": now,
        "exp": now + expires_in,
        "tenant_id": str(tenant_id) if tenant_id else "",
        "store_id": str(store_id) if store_id else "",
        "store_ids": [str(s) for s in (store_ids or [])],
        "role": role or "user",
    }

    encoded_header = _b64url_encode(json.dumps(header))
    encoded_payload = _b64url_encode(json.dumps(payload))
    signing_input = f"{encoded_header}.{encoded_payload}".encode('utf-8')

    signature = hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    encoded_signature = _b64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


class HavanoPowerSyncController(http.Controller):

    def _get_powersync_config(self):
        """Retrieve PowerSync URL and secret from ir.config_parameter."""
        ICP = request.env['ir.config_parameter'].sudo()
        powersync_url = ICP.get_param('havano.powersync_url', DEFAULT_POWERSYNC_URL)
        powersync_secret = ICP.get_param('havano.powersync_secret', DEFAULT_JWT_SECRET)
        return powersync_url, powersync_secret

    def _verify_auth(self):
        """Authenticate request from Bearer or Basic authorization header."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        user_env = request.env

        # 1. Active session
        if request.session.uid:
            user = user_env['res.users'].sudo().browse(request.session.uid)
            if user.exists():
                return user

        # 2. Bearer / Basic Auth token
        if auth_header:
            token = auth_header.replace('Bearer ', '').replace('Basic ', '').strip()
            try:
                decoded = base64.b64decode(token).decode('utf-8')
                if ':' in decoded:
                    login, pwd = decoded.split(':', 1)
                    user = user_env['res.users'].sudo().search([('login', '=', login)], limit=1)
                    if user:
                        return user
            except Exception:
                pass

            user = user_env['res.users'].sudo().search([
                '|', ('login', '=', token), ('id', '=', token)
            ], limit=1)
            if user:
                return user

        return None

    # =========================================================================
    # 1. POWERSYNC TOKEN ENDPOINT
    # =========================================================================
    @http.route('/api/powersync/token', type='http', auth='public', methods=['GET', 'OPTIONS'], csrf=False, cors='*')
    def get_powersync_token(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response('{}', headers=[('Content-Type', 'application/json')], status=200)

        user = self._verify_auth()
        if not user:
            return request.make_response(
                json.dumps({'error': 'Unauthorized'}),
                headers=[('Content-Type', 'application/json')],
                status=401
            )

        tenant = user.tenant_id
        if not tenant:
            return request.make_response(
                json.dumps({'error': 'User has no associated tenant'}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        req_store_id = kw.get('shop_id') or request.httprequest.headers.get('shop_id')
        if not req_store_id and user.store_ids:
            req_store_id = user.store_ids[0].id

        powersync_url, powersync_secret = self._get_powersync_config()

        jwt_token = generate_powersync_jwt(
            user_id=user.id,
            tenant_id=tenant.id,
            store_id=req_store_id,
            store_ids=user.store_ids.ids if user.store_ids else [],
            role=user.havano_role,
            secret_key=powersync_secret,
            expires_in=2592000  # 30 days
        )

        response_data = {
            'token': jwt_token,
            'powersync_url': powersync_url,
            'expires_in': 2592000,
            'tenant_id': str(tenant.id),
            'user_id': str(user.id),
            'store_id': str(req_store_id) if req_store_id else None,
        }

        return request.make_response(
            json.dumps(response_data),
            headers=[('Content-Type', 'application/json')],
            status=200
        )

    # =========================================================================
    # 2. POWERSYNC BATCH UPLOAD ENDPOINT (OFFLINE MUTATIONS)
    # =========================================================================
    @http.route('/api/powersync/upload', type='http', auth='public', methods=['POST', 'OPTIONS'], csrf=False, cors='*')
    def powersync_upload(self, **kw):
        if request.httprequest.method == 'OPTIONS':
            return request.make_response('{}', headers=[('Content-Type', 'application/json')], status=200)

        user = self._verify_auth()
        if not user:
            return request.make_response(
                json.dumps({'error': 'Unauthorized'}),
                headers=[('Content-Type', 'application/json')],
                status=401
            )

        try:
            body = json.loads(request.httprequest.data.decode('utf-8'))
        except Exception as e:
            return request.make_response(
                json.dumps({'error': f'Invalid JSON payload: {e}'}),
                headers=[('Content-Type', 'application/json')],
                status=400
            )

        batch = body.get('batch', [])
        if not batch:
            return request.make_response(
                json.dumps({'success': True, 'processed': 0}),
                headers=[('Content-Type', 'application/json')],
                status=200
            )

        results = []
        SaleModel = request.env['havanoposdesk.sale'].sudo()
        CustomerModel = request.env['havanoposdesk.customer'].sudo()
        ShiftModel = request.env['havanoposdesk.shift'].sudo()
        PaymentModel = request.env['havanoposdesk.payment'].sudo()
        AccountModel = request.env['havanoposdesk.account'].sudo()

        cr = request.env.cr
        processed_count = 0

        for item in batch:
            mutation_type = item.get('type')

            try:
                with cr.savepoint():
                    # ---------------------------------------------------------
                    # 1. SALE MUTATION
                    # ---------------------------------------------------------
                    if mutation_type == 'sale':
                        sale_data = item.get('sale', {})
                        items = item.get('items', [])
                        payments = item.get('payments', [])
                        local_invoice_id = sale_data.get('local_invoice_id')

                        # Check for idempotency
                        existing_sale = SaleModel.search([
                            ('tenant_id', '=', user.tenant_id.id),
                            ('local_invoice_id', '=', local_invoice_id)
                        ], limit=1)

                        if existing_sale:
                            results.append({'sale_id': item.get('sale_id'), 'status': 'already_exists', 'id': existing_sale.id, 'name': existing_sale.name})
                            continue

                        # Resolve customer
                        customer_name = sale_data.get('customer_name') or 'Walk-in Customer'
                        customer = CustomerModel.search([
                            ('tenant_id', '=', user.tenant_id.id),
                            ('name', '=', customer_name)
                        ], limit=1)

                        if not customer:
                            customer = CustomerModel.create({
                                'name': customer_name,
                                'customer_name': customer_name,
                                'tenant_id': user.tenant_id.id,
                            })

                        # Resolve store
                        store = False
                        warehouse_name = sale_data.get('warehouse') or ''
                        if warehouse_name:
                            store = request.env['havanoposdesk.store'].sudo().search([
                                ('name', '=', warehouse_name),
                                ('tenant_id', '=', user.tenant_id.id)
                            ], limit=1)
                        if not store and sale_data.get('store_id'):
                            store = request.env['havanoposdesk.store'].sudo().browse(int(sale_data['store_id']))
                        if not store or not store.exists():
                            store = user.default_store_id or (user.store_ids[0] if user.store_ids else False)

                        sale_tenant_id = store.tenant_id.id if (store and store.tenant_id) else user.tenant_id.id

                        sale_vals = {
                            'tenant_id': sale_tenant_id,
                            'customer': customer.id,
                            'local_invoice_id': local_invoice_id,
                            'grand_total': float(sale_data.get('grand_total') or 0.0),
                            'total_tax': float(sale_data.get('total_tax_amount') or 0.0),
                            'discount_amount': float(sale_data.get('discount_amount') or 0.0),
                            'paid_amount': float(sale_data.get('paid_amount') or 0.0),
                            'change_amount': float(sale_data.get('change_amount') or 0.0),
                            'currency': sale_data.get('currency') or 'USD',
                            'price_list': sale_data.get('price_list') or '',
                            'store': store.name if store else '',
                            'store_id': store.id if store else False,
                            'posting_date': sale_data.get('posting_date') or fields.Date.context_today(user),
                            'is_return': bool(sale_data.get('is_return')),
                            'is_quotation': bool(sale_data.get('is_quotation')),
                            'fiscal_code': sale_data.get('fiscal_code') or '',
                            'qr_code': sale_data.get('fiscal_qr_code') or '',
                        }

                        new_sale = SaleModel.create(sale_vals)

                        # Create sale lines
                        for line in items:
                            prod = request.env['havanoposdesk.product'].sudo().search([
                                ('tenant_id', '=', sale_tenant_id),
                                ('item_code', '=', line.get('item_code'))
                            ], limit=1)

                            request.env['havanoposdesk.sale_line'].sudo().create({
                                'sale_id': new_sale.id,
                                'product_id': prod.id if prod else False,
                                'name': line.get('item_name') or (prod.name if prod else 'Item'),
                                'qty': float(line.get('qty') or 1.0),
                                'rate': float(line.get('rate') or 0.0),
                                'amount': float(line.get('amount') or 0.0),
                                'tax_amount': float(line.get('tax_amount') or 0.0),
                                'tenant_id': sale_tenant_id,
                            })

                        # Create payment records
                        for p in payments:
                            method_name = p.get('payment_method') or 'Cash'
                            acc = AccountModel.search([
                                ('tenant_id', '=', sale_tenant_id),
                                ('name', '=ilike', method_name)
                            ], limit=1)
                            if not acc:
                                acc = AccountModel.search([
                                    ('tenant_id', '=', sale_tenant_id),
                                    ('type', '=', 'Cash')
                                ], limit=1)

                            PaymentModel.create({
                                'tenant_id': sale_tenant_id,
                                'sale_id': new_sale.id,
                                'account_id': acc.id if acc else False,
                                'amount': float(p.get('amount') or 0.0),
                                'amount_base': float(p.get('base_amount') or p.get('amount') or 0.0),
                                'exchange_rate': float(p.get('exchange_rate') or 1.0),
                                'reference': p.get('reference') or local_invoice_id or '',
                            })

                        results.append({'sale_id': item.get('sale_id'), 'status': 'created', 'server_id': new_sale.id, 'name': new_sale.name})
                        processed_count += 1

                    # ---------------------------------------------------------
                    # 2. SHIFT MUTATION (OPEN / CLOSE)
                    # ---------------------------------------------------------
                    elif mutation_type == 'shift':
                        shift_data = item.get('shift', {})
                        shift_action = shift_data.get('action') or ('close' if shift_data.get('state') == 'closed' else 'open')

                        if shift_action == 'open':
                            new_shift = ShiftModel.create({
                                'tenant_id': user.tenant_id.id,
                                'user_id': user.id,
                                'store_id': shift_data.get('store_id') or (user.default_store_id.id if user.default_store_id else False),
                                'terminal_id': shift_data.get('terminal_id'),
                                'opening_cash': float(shift_data.get('opening_cash') or 0.0),
                                'start_date': shift_data.get('start_date') or fields.Datetime.now(),
                                'state': 'open',
                            })
                            results.append({'shift_id': item.get('client_id'), 'server_id': new_shift.id, 'status': 'opened', 'name': new_shift.name})
                            processed_count += 1

                        elif shift_action == 'close':
                            shift_id = shift_data.get('shift_id') or shift_data.get('server_id') or shift_data.get('id')
                            shift_rec = False
                            if shift_id and str(shift_id).isdigit():
                                shift_rec = ShiftModel.browse(int(shift_id))

                            if not shift_rec or not shift_rec.exists():
                                # Fallback search: find active open shift for this user and store
                                shift_rec = ShiftModel.search([
                                    ('tenant_id', '=', user.tenant_id.id),
                                    ('user_id', '=', user.id),
                                    ('state', '=', 'open')
                                ], limit=1)

                            if shift_rec and shift_rec.exists() and shift_rec.tenant_id.id == user.tenant_id.id:
                                shift_rec.write({
                                    'actual_cash': float(shift_data.get('actual_cash') or 0.0),
                                    'end_date': shift_data.get('end_date') or fields.Datetime.now(),
                                    'state': 'closed',
                                })
                                results.append({'shift_id': item.get('client_id'), 'server_id': shift_rec.id, 'status': 'closed', 'name': shift_rec.name})
                                processed_count += 1
                            else:
                                results.append({'shift_id': item.get('client_id'), 'status': 'error', 'error': 'Open shift not found for closing'})

                    # ---------------------------------------------------------
                    # 3. CUSTOMER MUTATION
                    # ---------------------------------------------------------
                    elif mutation_type == 'customer':
                        cust_data = item.get('customer', {})
                        new_cust = CustomerModel.create({
                            'name': cust_data.get('customer_name') or cust_data.get('name'),
                            'customer_name': cust_data.get('customer_name'),
                            'currency': cust_data.get('currency') or 'USD',
                            'custom_cost_center': cust_data.get('custom_cost_center'),
                            'custom_customer_tin': cust_data.get('custom_customer_tin') or '',
                            'custom_customer_vat': cust_data.get('custom_customer_vat') or '',
                            'custom_telephone_number': cust_data.get('custom_telephone_number') or '',
                            'custom_email_address': cust_data.get('custom_email_address') or '',
                            'tenant_id': user.tenant_id.id,
                        })
                        results.append({'client_id': item.get('client_id'), 'status': 'created', 'id': new_cust.id})
                        processed_count += 1

            except Exception as e:
                _logger.exception("Error processing PowerSync upload item: %s", item)
                results.append({'item': item, 'status': 'error', 'error': str(e)})

        return request.make_response(
            json.dumps({'success': True, 'processed': processed_count, 'results': results}),
            headers=[('Content-Type', 'application/json')],
            status=200
        )
