import re

with open('inventory/controllers/api.py', 'r') as f:
    content = f.read()

def replace_helper(match):
    return """    def _get_direct_rate(self, env, currency_id, tenant=None):
        if tenant:
            env.cr.execute("SELECT rate FROM res_currency_rate WHERE currency_id = %s AND tenant_id = %s ORDER BY name DESC LIMIT 1", (currency_id, tenant.id))
        else:
            env.cr.execute("SELECT rate FROM res_currency_rate WHERE currency_id = %s ORDER BY name DESC LIMIT 1", (currency_id,))
        res = env.cr.fetchone()
        if res and res[0]:
            return res[0]
        return 1.0
"""

pattern = r"""    def _get_direct_rate\(self, env, currency_id, tenant=None\):
        domain = \[\('currency_id', '=', currency_id\)\]
        if tenant:
            domain\.append\(\('tenant_id', '=', tenant\.id\)\)
        rate_record = env\['res\.currency\.rate'\]\.sudo\(\)\.search\(domain, order='name DESC', limit=1\)
        if rate_record:
            return rate_record\.rate or 1\.0
        return 1\.0
"""

new_content = re.sub(pattern, replace_helper, content)

with open('inventory/controllers/api.py', 'w') as f:
    f.write(new_content)

print("Direct SQL rate fetcher added.")
