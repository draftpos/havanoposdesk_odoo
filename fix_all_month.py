import os
import re

def fix_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.xml'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r') as f:
                    content = f.read()

                # Fix for <filter name="this_month" ... domain="[...]"/>
                # We need to replace the whole line with the correct date="date" default_period="this_month"
                # The field name could be 'date', 'create_date', or 'posting_date'
                
                # Regex for <filter ... name="this_month" domain="[...]" />
                pattern = r'<filter\s+string="This Month"\s+name="this_month"\s+domain="\[\(\'(.*?)\',\s*\'&gt;=\',\s*context_today\(\)\.strftime\(\'%Y-%m-01 00:00:00\'\)\)\]"\s*/>'
                
                def replacement(match):
                    field_name = match.group(1)
                    return f'<filter string="This Month" name="this_month" date="{field_name}" default_period="this_month" />'
                
                content = re.sub(pattern, replacement, content)

                # Fix for group_month
                group_pattern = r'<filter\s+string="This Month"\s+name="group_month"\s+domain="\[\(\'(.*?)\',\s*\'&gt;=\',\s*context_today\(\)\.strftime\(\'%Y-%m-01 00:00:00\'\)\)\]"\s*context="\{\'group_by\':\s*\'.*?\'\}"\s*/>'
                def group_replacement(match):
                    field_name = match.group(1)
                    # We might need to keep the context group_by... Wait, if it's a date group, Odoo might just use the date field.
                    # But actually group_by is typically just date="date" for grouping in some cases, or maybe we just don't touch group_month?
                    # The user said "when i filter by month". group_month doesn't trigger the filter tag!
                    # Actually, for group_month, Odoo doesn't use `date="date"` the same way. It uses `context="{'group_by': 'date:month'}"`
                    # If I change group_month to `date="date" default_period="this_month"`, it becomes a filter, not a group by!
                    # Wait, in the original `sale_views.xml`, they had:
                    # <filter string="This Month" name="group_month" date="date" default_period="month" context="{'group_by': 'date:month'}" />
                    # Let's restore that original format but with default_period="this_month".
                    group_by_str = f"{{'group_by': '{field_name}:month'}}"
                    return f'<filter string="This Month" name="group_month" date="{field_name}" default_period="this_month" context="{group_by_str}" />'

                content = re.sub(group_pattern, group_replacement, content)

                with open(filepath, 'w') as f:
                    f.write(content)

fix_files('/Users/josphatndhlovu/Documents/WORK/Showline/COMMUNITY/odoo-19.0/custom-addons/havanoposdesk_odoo')
