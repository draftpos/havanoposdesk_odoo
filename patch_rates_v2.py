import re
with open('inventory/controllers/api.py', 'r') as f:
    content = f.read()

def replace_block(match):
    full = match.group(0)
    company_var = match.group(1)
    from_cur = match.group(2)
    to_cur = match.group(3)
    
    return f"""                    company = {company_var}
                    rates = user_env['res.currency'].sudo()._get_rates(company, today_date) if 'user_env' in locals() else env['res.currency'].sudo()._get_rates(company, today_date)
                    from_rate = rates.get({from_cur}.id, 1.0)
                    to_rate = rates.get({to_cur}.id, 1.0)
                    rate_val = to_rate / from_rate if from_rate else 1.0"""

pattern = r"""                    company = ([^\n]+)
                    from_rate = ([a-zA-Z0-9_]+)\.with_company\(company\)\.rate or 1\.0
                    to_rate = ([a-zA-Z0-9_]+)\.with_company\(company\)\.rate or 1\.0
                    rate_val = to_rate / from_rate"""

new_content = re.sub(pattern, replace_block, content)

with open('inventory/controllers/api.py', 'w') as f:
    f.write(new_content)

print(f"Replaced occurrences.")
