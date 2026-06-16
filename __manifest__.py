{
    'name': 'Havano ERP',
    'version': '1.0',
    'category': 'Sales/Point of Sale',
    'summary': 'Unified ERP backend serving Flutter POS app and Odoo UI',
    'description': """
        Havano ERP Odoo App.
        Manages Inventory, Products, Sales, Suppliers, and multi-tenancy.
        Provides JSON REST API for the Flutter Havano POS frontend.
    """,
    'author': 'Havano',
    'depends': ['base', 'web'],
    'data': [
        'security/ir.model.access.csv',
        'core/views/menus.xml',
        'core/views/tenant_views.xml',
        'inventory/views/category_views.xml',
        'inventory/views/uom_views.xml',
        'inventory/views/product_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
