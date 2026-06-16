from odoo import http
from odoo.http import request
import json

class HavanoPOSDeskAPI(http.Controller):

    # PRODUCTS
    @http.route('/api/products/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_products(self, **kw):
        if request.httprequest.method == 'GET':
            products = request.env['havanoposdesk.product'].sudo().search([])
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
                })
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            data = json.loads(request.httprequest.data)
            
            # Ensure a tenant exists
            tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            if not tenant:
                tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                
            vals = {
                'name': data.get('name'),
                'item_code': data.get('item_code'),
                'buying_price': data.get('buying_price', 0.0),
                'selling_price': data.get('selling_price', 0.0),
                'color_hex': data.get('color_hex'),
                'track_qty': data.get('track_qty', True),
                'tenant_id': tenant.id,
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
            }
            return request.make_response(json.dumps(res_data), headers=[('Content-Type', 'application/json')], status=201)

    # CATEGORIES
    @http.route('/api/categories/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_categories(self, **kw):
        if request.httprequest.method == 'GET':
            categories = request.env['havanoposdesk.category'].sudo().search([])
            data = [{'id': c.id, 'name': c.name} for c in categories]
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            data = json.loads(request.httprequest.data)
            tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            if not tenant:
                tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                
            cat = request.env['havanoposdesk.category'].sudo().create({
                'name': data.get('name'),
                'tenant_id': tenant.id,
            })
            return request.make_response(json.dumps({'id': cat.id, 'name': cat.name}), headers=[('Content-Type', 'application/json')], status=201)

    # UOMS
    @http.route('/api/uoms/', auth='public', methods=['GET', 'POST'], type='http', csrf=False, cors='*')
    def handle_uoms(self, **kw):
        if request.httprequest.method == 'GET':
            uoms = request.env['havanoposdesk.uom'].sudo().search([])
            data = [{'id': u.id, 'name': u.name, 'abbreviation': u.abbreviation} for u in uoms]
            return request.make_response(json.dumps(data), headers=[('Content-Type', 'application/json')])
        
        elif request.httprequest.method == 'POST':
            data = json.loads(request.httprequest.data)
            tenant = request.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            if not tenant:
                tenant = request.env['havanoposdesk.tenant'].sudo().create({'name': 'Default Tenant'})
                
            uom = request.env['havanoposdesk.uom'].sudo().create({
                'name': data.get('name'),
                'abbreviation': data.get('abbreviation'),
                'tenant_id': tenant.id,
            })
            return request.make_response(json.dumps({'id': uom.id, 'name': uom.name, 'abbreviation': uom.abbreviation}), headers=[('Content-Type', 'application/json')], status=201)
