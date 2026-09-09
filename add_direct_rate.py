import re

with open('inventory/controllers/api.py', 'r') as f:
    content = f.read()

helper_method = """
    def _get_direct_rate(self, env, currency_id, tenant=None):
        domain = [('currency_id', '=', currency_id)]
        if tenant:
            domain.append(('tenant_id', '=', tenant.id))
        rate_record = env['res.currency.rate'].sudo().search(domain, order='name DESC', limit=1)
        if rate_record:
            return getattr(rate_record, 'company_rate', rate_record.rate) or 1.0
        return 1.0
"""

# Insert the helper method after the class definition
class_def = "class HavanoPOSDeskAPI(http.Controller):"
content = content.replace(class_def, class_def + helper_method)

# Now replace the rates block
def replace_block(match):
    full = match.group(0)
    company_var = match.group(1)
    from_cur = match.group(2)
    to_cur = match.group(3)
    
    return f"""                    from_rate = self._get_direct_rate(user_env if 'user_env' in locals() else env, {from_cur}.id, tenant if 'tenant' in locals() else None)
                    to_rate = self._get_direct_rate(user_env if 'user_env' in locals() else env, {to_cur}.id, tenant if 'tenant' in locals() else None)
                    rate_val = to_rate / from_rate if from_rate else 1.0"""

pattern = r"""                    company = ([^\n]+)
                    rates = user_env\['res\.currency'\]\.sudo\(\)\._get_rates\(company, fields\.Datetime\.now\(\)\) if 'user_env' in locals\(\) else env\['res\.currency'\]\.sudo\(\)\._get_rates\(company, fields\.Datetime\.now\(\)\)
                    from_rate = rates\.get\(([a-zA-Z0-9_]+)\.id, 1\.0\)
                    to_rate = rates\.get\(([a-zA-Z0-9_]+)\.id, 1\.0\)
                    rate_val = to_rate / from_rate if from_rate else 1\.0"""

new_content = re.sub(pattern, replace_block, content)

with open('inventory/controllers/api.py', 'w') as f:
    f.write(new_content)

print("Direct rate fetcher added and occurrences replaced.")
