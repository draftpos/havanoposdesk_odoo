import glob
import re
files = glob.glob('**/*_views.xml', recursive=True)
for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = content.replace('havanoposdesk_odoo.', 'havanoposdesk_odoo.')
    if content != new_content:
        with open(file, 'w', encoding='utf-8') as f:
            f.write(new_content)
print('Fixed module name case in views')

