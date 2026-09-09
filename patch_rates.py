import re
with open('inventory/controllers/api.py', 'r') as f:
    content = f.read()

def replace_block(match):
    full = match.group(0)
    to_cur = match.group(1)
    from_cur = match.group(2)
    company_var = match.group(3)
    
    return f"""                    company = {company_var}
                    from_rate = {from_cur}.with_company(company).rate or 1.0
                    to_rate = {to_cur}.with_company(company).rate or 1.0
                    rate_val = to_rate / from_rate"""

pattern = r"""                    try:
                        rate_val = ([a-zA-Z0-9_]+)\._get_conversion_rate\(([a-zA-Z0-9_]+), \1, ([^,]+), today_date\)
                    except Exception:
                        rate_val = \1\.rate or 1\.0"""

new_content = re.sub(pattern, replace_block, content)

with open('inventory/controllers/api.py', 'w') as f:
    f.write(new_content)

print(f"Replaced {content.count('_get_conversion_rate')} occurrences.")
