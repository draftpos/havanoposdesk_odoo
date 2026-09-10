with open('inventory/controllers/api.py', 'r') as f:
    content = f.read()

new_impl = """# SHIFT MANAGEMENT SYSTEM
    @http.route('/api/method/saas_api.www.api.open_shift', auth='public', methods=['POST', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_open_shift(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)

        token = request.httprequest.headers.get('Authorization')
        uid, login = self._verify_token(token)
        if not uid:
            user = self._get_user()
            uid = user.id
            if not uid:
                return self._make_json_response({"message": {"status": "error", "message": "Unauthorized"}}, status=401)

        params = self._get_request_json()
        terminal_id = params.get('terminal_id')
        store_id = params.get('store_id')
        opening_cash = float(params.get('opening_cash', 0.0))

        env = request.env(user=uid)
        
        # Check if already open shift exists
        existing_shift = env['havanoposdesk.shift'].sudo().search([
            ('user_id', '=', uid),
            ('state', '=', 'open')
        ], limit=1)
        
        if existing_shift:
            return self._make_json_response({
                "message": {
                    "status": "success",
                    "shift": {
                        "id": existing_shift.id,
                        "name": existing_shift.name,
                        "status": "Open",
                        "opening_time": str(existing_shift.start_date)
                    }
                }
            })
            
        if not store_id:
            store = env['havanoposdesk.store'].sudo().search([], limit=1)
            store_id = store.id if store else False
            
        shift = env['havanoposdesk.shift'].sudo().create({
            'user_id': uid,
            'store_id': store_id,
            'terminal_id': terminal_id,
            'opening_cash': opening_cash,
            'state': 'open'
        })
        
        return self._make_json_response({
            "message": {
                "status": "success",
                "shift": {
                    "id": shift.id,
                    "name": shift.name,
                    "status": "Open",
                    "opening_time": str(shift.start_date)
                }
            }
        })

    @http.route('/api/method/saas_api.www.api.close_shift', auth='public', methods=['POST', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_close_shift(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)

        token = request.httprequest.headers.get('Authorization')
        uid, login = self._verify_token(token)
        if not uid:
            user = self._get_user()
            uid = user.id
            if not uid:
                return self._make_json_response({"message": {"status": "error", "message": "Unauthorized"}}, status=401)

        params = self._get_request_json()
        env = request.env(user=uid)
        
        shift = env['havanoposdesk.shift'].sudo().search([
            ('user_id', '=', uid),
            ('state', '=', 'open')
        ], limit=1)
        
        if not shift:
            return self._make_json_response({"message": {"status": "error", "message": "No open shift found"}}, status=404)
            
        # Update shift with closing details from POS
        update_vals = {
            'actual_cash': float(params.get('actual_cash', 0.0)),
        }
        
        # If POS sends breakdowns, use them
        if 'amount_cash' in params:
            update_vals['amount_cash'] = float(params.get('amount_cash', 0.0))
        if 'amount_card' in params:
            update_vals['amount_card'] = float(params.get('amount_card', 0.0))
        if 'amount_mobile' in params:
            update_vals['amount_mobile'] = float(params.get('amount_mobile', 0.0))
        if 'amount_bank' in params:
            update_vals['amount_bank'] = float(params.get('amount_bank', 0.0))
        if 'amount_other' in params:
            update_vals['amount_other'] = float(params.get('amount_other', 0.0))
        if 'total_expenses' in params:
            update_vals['total_expenses'] = float(params.get('total_expenses', 0.0))
        if 'total_credit_notes' in params:
            update_vals['total_credit_notes'] = float(params.get('total_credit_notes', 0.0))
            
        shift.write(update_vals)
        shift.action_close_shift()
        
        return self._make_json_response({
            "message": {
                "status": "success",
                "shift": {
                    "id": shift.id,
                    "name": shift.name,
                    "status": "Closed",
                    "closing_time": str(shift.end_date),
                    "expected_cash": shift.expected_cash,
                    "actual_cash": shift.actual_cash,
                    "difference": shift.cash_difference
                }
            }
        })

    @http.route('/api/method/saas_api.www.api.get_current_shift', auth='public', methods=['GET', 'OPTIONS'], type='http', csrf=False, cors='*')
    def api_get_current_shift(self, **kwargs):
        if request.httprequest.method == 'OPTIONS':
            return self._make_json_response({}, status=200)

        token = request.httprequest.headers.get('Authorization')
        uid, login = self._verify_token(token)
        if not uid:
            user = self._get_user()
            uid = user.id
            if not uid:
                return self._make_json_response({"message": {"status": "error", "message": "Unauthorized"}}, status=401)

        env = request.env(user=uid)
        shift = env['havanoposdesk.shift'].sudo().search([
            ('user_id', '=', uid),
            ('state', '=', 'open')
        ], limit=1)
        
        if not shift:
            return self._make_json_response({
                "message": {
                    "status": "success",
                    "shift": None
                }
            })
            
        return self._make_json_response({
            "message": {
                "status": "success",
                "shift": {
                    "id": shift.id,
                    "name": shift.name,
                    "status": "Open",
                    "opening_time": str(shift.start_date)
                }
            }
        })
"""

# Let's find the blocks by splitting with "# SHIFT MANAGEMENT SYSTEM"
parts = content.split('# SHIFT MANAGEMENT SYSTEM')

if len(parts) >= 2:
    new_parts = [parts[0]]
    for i in range(1, len(parts)):
        part = parts[i]
        # We need to find the end of api_get_current_shift
        # A simple way is to find the next method definition that is NOT open/close/get_current shift, or we just find the end of the get_current_shift function block
        
        # We know get_current_shift ends with "opening_time": time.strftime('%Y-%m-%d 00:00:00')\n                }\n            }\n        })\n"
        
        end_idx = part.find("'%Y-%m-%d 00:00:00'")
        if end_idx != -1:
            end_bracket_idx = part.find("})", end_idx) + 2
            remainder = part[end_bracket_idx:]
            
            # Remove any trailing newlines and whitespace before the next function definition
            remainder = remainder.lstrip(' \t\n\r')
            
            # Instead of appending part, we append the replacement and the remainder
            new_parts.append(new_impl + remainder)
        else:
            print(f"Could not find end of get_current_shift in part {i}")
            new_parts.append('# SHIFT MANAGEMENT SYSTEM' + part)
            
    final_content = "\n\n    ".join(new_parts)
    # The first join adds some indentation, actually we should just concatenate because we split without preserving the exact whitespace before "# SHIFT MANAGEMENT SYSTEM"
    
    # Wait, the split removed '# SHIFT MANAGEMENT SYSTEM'. We should reconstruct it properly.
    final_parts = [parts[0]]
    for i in range(1, len(parts)):
        part = parts[i]
        end_idx = part.find("'%Y-%m-%d 00:00:00'")
        if end_idx != -1:
            end_bracket_idx = part.find("})", end_idx) + 2
            remainder = part[end_bracket_idx:]
            # Ensure proper line breaks
            final_parts.append("\n    " + new_impl + "\n\n    " + remainder.lstrip())
        else:
            final_parts.append("\n    # SHIFT MANAGEMENT SYSTEM" + part)
            
    with open('inventory/controllers/api.py', 'w') as f:
        f.write("".join(final_parts))
    print(f"Patched {len(parts)-1} occurrences.")
else:
    print("Could not find '# SHIFT MANAGEMENT SYSTEM'")

