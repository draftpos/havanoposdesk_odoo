import os
import xml.etree.ElementTree as ET

# Map of action ids to their full definitions from other files
# E.g. action_havanoposdesk_category -> {"name": "Categories", "res_model": "havanoposdesk.category"}
action_map = {
    'action_havanoposdesk_category': {'name': 'Categories', 'res_model': 'havanoposdesk.category'},
    'action_havanoposdesk_pricelist': {'name': 'Pricelists', 'res_model': 'havanoposdesk.pricelist'},
    'action_havanoposdesk_uom': {'name': 'UOMs', 'res_model': 'havanoposdesk.uom'},
    'action_havanoposdesk_product': {'name': 'Products', 'res_model': 'havanoposdesk.product'},
    'action_havanoposdesk_stock_adjustment': {'name': 'Stock Adjustments', 'res_model': 'havanoposdesk.stock.adjustment'},
    'action_havanoposdesk_stock_valuation': {'name': 'Stock Valuation', 'res_model': 'havanoposdesk.stock.valuation'},
    'action_havanoposdesk_stock_ledger': {'name': 'Stock Ledger', 'res_model': 'havanoposdesk.stock.ledger'},
    'action_havanoposdesk_account': {'name': 'Accounts', 'res_model': 'havanoposdesk.account'},
    'action_havanoposdesk_tax': {'name': 'Taxes', 'res_model': 'havanoposdesk.tax'},
    'action_havanoposdesk_payment': {'name': 'Payments', 'res_model': 'havanoposdesk.payment'},
    'action_havanoposdesk_expense': {'name': 'Expenses', 'res_model': 'havanoposdesk.expense'},
    'action_havanoposdesk_supplier': {'name': 'Suppliers', 'res_model': 'havanoposdesk.supplier'},
    'action_havanoposdesk_purchase': {'name': 'Purchases', 'res_model': 'havanoposdesk.purchase'},
    'action_havanoposdesk_customer': {'name': 'Customers', 'res_model': 'havanoposdesk.customer'},
    'action_havanoposdesk_customer_group': {'name': 'Customer Groups', 'res_model': 'havanoposdesk.customer.group'},
    'action_sales_operations': {'name': 'Sales Operations', 'res_model': 'havanoposdesk.sale'},
    'action_cashier_sales_report': {'name': 'Cashier Sales Report', 'res_model': 'havanoposdesk.cashier.sales.report'},
    'action_category_sales_report': {'name': 'Category Sales Report', 'res_model': 'havanoposdesk.category.sales.report'},
    'action_daily_sales_report': {'name': 'Daily Sales Report', 'res_model': 'havanoposdesk.daily.sales.report'},
    'action_item_profitability_report': {'name': 'Item Profitability Report', 'res_model': 'havanoposdesk.item.profitability.report'},
    'action_terminal_sales_report': {'name': 'Terminal Sales Report', 'res_model': 'havanoposdesk.terminal.sales.report'},
}

def patch_file(filepath):
    print(f"Patching {filepath}")
    tree = ET.parse(filepath)
    root = tree.getroot()
    modified = False
    
    for record in root.findall('.//record[@model="ir.actions.act_window"]'):
        action_id = record.get('id')
        if action_id in action_map:
            # Check if name or res_model are missing
            has_name = any(field.get('name') == 'name' for field in record.findall('field'))
            has_model = any(field.get('name') == 'res_model' for field in record.findall('field'))
            
            if not has_name:
                name_field = ET.Element('field', name='name')
                name_field.text = action_map[action_id]['name']
                name_field.tail = '\n            '
                record.insert(0, name_field)
                modified = True
                
            if not has_model:
                model_field = ET.Element('field', name='res_model')
                model_field.text = action_map[action_id]['res_model']
                model_field.tail = '\n            '
                record.insert(0 if has_name else 1, model_field)
                modified = True
                
    if modified:
        with open(filepath, 'wb') as f:
            tree.write(f, encoding='utf-8', xml_declaration=True)
            f.write(b'\n')
        print(f"Saved {filepath}")

import glob
for file in glob.glob('*/views/*_mobile_kanban_views.xml'):
    patch_file(file)

