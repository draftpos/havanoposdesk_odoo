import xmlrpc.client

common = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/common')
uid = common.authenticate('odoo_driving_backedup', 'admin', 'admin', {})
models = xmlrpc.client.ServerProxy('http://localhost:8069/xmlrpc/2/object')

# Check if new slot fields exist on the running server
fields = models.execute_kw('odoo_driving_backedup', uid, 'admin', 'havanoposdesk.product.variant', 'fields_get',
    [['attribute_value_1_id', 'attribute_value_2_id', 'attribute_value_3_id', 'attribute_value_4_id', 'attribute_value_5_id', 'name', 'attribute_value_ids']],
    {'attributes': ['string', 'type']})
print('Variant fields:', fields)
