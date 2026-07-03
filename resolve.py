import re
files = [
    '__manifest__.py',
    'core/models/__init__.py',
    'core/models/res_config_settings.py',
    'core/views/menus.xml',
    'static/src/js/whitelabel.js'
]
for file in files:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(r'<<<<<<< HEAD\n(.*?)\n=======\n(.*?)\n>>>>>>> [a-f0-9]+', re.DOTALL)
    def replacer(match):
        return match.group(1) + '\n' + match.group(2)
    new_content = pattern.sub(replacer, content)
    with open(file, 'w', encoding='utf-8') as f:
        f.write(new_content)
print("Conflicts resolved.")
