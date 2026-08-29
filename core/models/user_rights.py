from odoo import models, fields, api, tools
from odoo.exceptions import AccessError
import logging

_logger = logging.getLogger(__name__)

class HavanoposdeskUserRightsProfile(models.Model):
    _name = 'havanoposdesk.user.rights.profile'
    _inherit = ['havanoposdesk.audit.mixin']
    _description = 'User Rights Profile'
    _order = 'name'

    name = fields.Char(string='Profile Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id
    )
    is_additional_tax_enabled = fields.Boolean(string='Is Additional Tax Enabled', default=False)
    food_tax = fields.Float(string='Food Tax %')
    tourism_tax = fields.Float(string='Tourism Tax %')
    
    @api.model
    def _get_havano_role_selection(self):
        roles = [
            ('admin', 'Admin'),
            ('user', 'Cashier')
        ]
        if self.env.user.id == 1 or getattr(self.env.user, 'havano_role', None) == 'super_admin':
            roles.insert(0, ('super_admin', 'Super Admin'))
        return roles

    havano_role = fields.Selection(selection='_get_havano_role_selection', string="Role", default='user')
    
    permission_ids = fields.One2many(
        'havanoposdesk.user.rights.permission', 
        'profile_id', 
        string='POS Permissions', 
        copy=True
    )
    
    backoffice_permission_ids = fields.One2many(
        'havanoposdesk.backoffice.permission', 
        'profile_id', 
        string='Back Office Permissions', 
        copy=True
    )
    bo_sales_ids = fields.One2many('havanoposdesk.backoffice.permission', 'profile_id', domain=[('category', '=', 'sales')], string='Sales')
    bo_purchases_ids = fields.One2many('havanoposdesk.backoffice.permission', 'profile_id', domain=[('category', '=', 'purchases')], string='Purchases')
    bo_inventory_ids = fields.One2many('havanoposdesk.backoffice.permission', 'profile_id', domain=[('category', '=', 'inventory')], string='Inventory')
    bo_accounting_ids = fields.One2many('havanoposdesk.backoffice.permission', 'profile_id', domain=[('category', '=', 'accounting')], string='Accounting')
    bo_settings_ids = fields.One2many('havanoposdesk.backoffice.permission', 'profile_id', domain=[('category', '=', 'settings')], string='Settings')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
            
            if 'permission_ids' not in vals or not vals['permission_ids']:
                features = [
                    'Dashboard', 'POS', 'Quotations', 'Sales', 'Products',
                    'Categories', 'Brands', 'Taxes', 'Stock Management',
                    'Payment Entries', 'Reports', 'Profit and Loss', 'Settings',
                    'Printer', 'Terminals', 'Stores', 'Suppliers', 'Customers',
                    'Expenses', 'User Profiles'
                ]
                permission_lines = []
                is_cashier = vals.get('havano_role') in ('user', 'cashier')
                for feature in features:
                    permission_lines.append((0, 0, {
                        'feature': feature,
                        'can_read': True,
                        'can_create': not is_cashier,
                        'can_update': not is_cashier,
                        'can_delete': not is_cashier,
                        'can_submit': not is_cashier,
                    }))
                vals['permission_ids'] = permission_lines

            if 'backoffice_permission_ids' not in vals or not vals['backoffice_permission_ids']:
                bo_features = [
                    'Sales Invoices', 'Purchases', 'Customers', 'Customer Groups',
                    'Taxes', 'Exchange Rate', 'Currencies', 'Stores', 'Users',
                    'User Rights Profiles', 'My Subscription', 'Chart of Accounts',
                    'Stock Transfers', 'Stock Adjustments', 'Stock Evaluations',
                    'Stock Ledger', 'Products', 'UOM', 'Pricelists', 'Categories',
                    'Item Profitability', 'Category Profitability', 'Sales Returns',
                    'Expense Posting', 'Payments', 'POS Terminals', 'Profit and Loss',
                    'Cash Balance', 'Daily Sales', 'Cashier Profitability', 'Shop Profitability',
                    'Suppliers', 'System Logs', 'Issues', 'Sync Issues', 'Configs',
                    'Settings', 'Dashboard', 'Tenants', 'Subscription Plans',
                    'Payment Providers', 'Support Tickets', 'My Preferences'
                ]
                bo_permission_lines = []
                is_cashier = vals.get('havano_role') in ('user', 'cashier')
                for feature in bo_features:
                    bo_permission_lines.append((0, 0, {
                        'feature': feature,
                        'is_full_access': not is_cashier,
                        'is_read_only': is_cashier,
                    }))
                vals['backoffice_permission_ids'] = bo_permission_lines
                
        records = super().create(vals_list)
        for record in records:
            if record.havano_role and record.tenant_id:
                users = self.env['res.users'].search([
                    ('tenant_id', '=', record.tenant_id.id),
                    ('havano_role', '=', record.havano_role),
                    ('user_rights_profile_id', '!=', record.id)
                ])
                if users:
                    users.sudo().with_context(bypass_sync_role_groups=True).write({'user_rights_profile_id': record.id})
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'havano_role' in vals:
            for record in self:
                if record.havano_role and record.tenant_id:
                    users = self.env['res.users'].search([
                        ('tenant_id', '=', record.tenant_id.id),
                        ('havano_role', '=', record.havano_role),
                        ('user_rights_profile_id', '!=', record.id)
                    ])
                    if users:
                        users.sudo().with_context(bypass_sync_role_groups=True).write({'user_rights_profile_id': record.id})
        return res


class HavanoposdeskUserRightsPermission(models.Model):
    _name = 'havanoposdesk.user.rights.permission'
    _description = 'User Rights Permission'
    _order = 'id'

    profile_id = fields.Many2one('havanoposdesk.user.rights.profile', string='Profile', ondelete='cascade', required=True)
    feature = fields.Selection([
        ('Dashboard', 'Dashboard'),
        ('POS', 'POS'),
        ('Quotations', 'Quotations'),
        ('Sales', 'Sales'),
        ('Products', 'Products'),
        ('Categories', 'Categories'),
        ('Brands', 'Brands'),
        ('Taxes', 'Taxes'),
        ('Stock Management', 'Stock Management'),
        ('Payment Entries', 'Payment Entries'),
        ('Reports', 'Reports'),
        ('Profit and Loss', 'Profit and Loss'),
        ('Settings', 'Settings'),
        ('Printer', 'Printer'),
        ('Terminals', 'Terminals'),
        ('Stores', 'Stores'),
        ('Suppliers', 'Suppliers'),
        ('Customers', 'Customers'),
        ('Expenses', 'Expenses'),
        ('Payroll', 'Payroll'),
        ('User Profiles', 'User Profiles')
    ], string='Feature', required=True)
    can_read = fields.Boolean(string='Read', default=True)
    can_create = fields.Boolean(string='Create', default=True)
    can_update = fields.Boolean(string='Update', default=True)
    can_delete = fields.Boolean(string='Delete', default=True)
    can_submit = fields.Boolean(string='Submit', default=True)

    _sql_constraints = [
        ('profile_feature_uniq', 'unique(profile_id, feature)', 'A feature permission already exists for this profile!')
    ]


class HavanoposdeskBackofficePermission(models.Model):
    _name = 'havanoposdesk.backoffice.permission'
    _description = 'Back Office Permission'
    _order = 'id'

    profile_id = fields.Many2one('havanoposdesk.user.rights.profile', string='Profile', ondelete='cascade', required=True)
    feature = fields.Selection([
        ('Sales Invoices', 'Sales Invoices'),
        ('Purchases', 'Purchases'),
        ('Customers', 'Customers'),
        ('Customer Groups', 'Customer Groups'),
        ('Taxes', 'Taxes'),
        ('Exchange Rate', 'Exchange Rate'),
        ('Currencies', 'Currencies'),
        ('Stores', 'Stores'),
        ('Users', 'Users'),
        ('User Rights Profiles', 'User Rights Profiles'),
        ('My Subscription', 'My Subscription'),
        ('Chart of Accounts', 'Chart of Accounts'),
        ('Stock Transfers', 'Stock Transfers'),
        ('Stock Adjustments', 'Stock Adjustments'),
        ('Stock Evaluations', 'Stock Evaluations'),
        ('Stock Ledger', 'Stock Ledger'),
        ('Products', 'Products'),
        ('UOM', 'UOM'),
        ('Pricelists', 'Pricelists'),
        ('Categories', 'Categories'),
        ('Item Profitability', 'Item Profitability'),
        ('Category Profitability', 'Category Profitability'),
        ('Sales Returns', 'Sales Returns'),
        ('Expense Posting', 'Expense Posting'),
        ('Payments', 'Payments'),
        ('POS Terminals', 'POS Terminals'),
        ('Profit and Loss', 'Profit and Loss'),
        ('Cash Balance', 'Cash Balance'),
        ('Daily Sales', 'Daily Sales'),
        ('Cashier Profitability', 'Cashier Profitability'),
        ('Shop Profitability', 'Shop Profitability'),
        ('Suppliers', 'Suppliers'),
        ('System Logs', 'System Logs'),
        ('Issues', 'Issues'),
        ('Sync Issues', 'Sync Issues'),
        ('Configs', 'Configs'),
        ('Settings', 'Settings'),
        ('Payroll', 'Payroll'),
        ('Dashboard', 'Dashboard'),
        ('Tenants', 'Tenants'),
        ('Subscription Plans', 'Subscription Plans'),
        ('Payment Providers', 'Payment Providers'),
        ('Support Tickets', 'Support Tickets'),
        ('My Preferences', 'My Preferences')
    ], string='Feature', required=True)

    category = fields.Selection([
        ('sales', 'Sales'),
        ('purchases', 'Purchases & Expenses'),
        ('inventory', 'Inventory'),
        ('accounting', 'Accounting & Finance'),
        ('settings', 'Settings & Configuration')
    ], string='Category', compute='_compute_category', store=True)

    @api.depends('feature')
    def _compute_category(self):
        cat_map = {
            'sales': ['Sales Invoices', 'Customers', 'Customer Groups', 'Sales Returns'],
            'purchases': ['Purchases', 'Expense Posting', 'Payments', 'Suppliers'],
            'inventory': ['Products', 'Categories', 'UOM', 'Pricelists', 'Stock Transfers', 'Stock Adjustments', 'Stock Evaluations', 'Stock Ledger', 'Stores'],
            'accounting': ['Taxes', 'Exchange Rate', 'Currencies', 'Chart of Accounts', 'Item Profitability', 'Category Profitability'],
            'settings': ['Users', 'User Rights Profiles', 'My Subscription', 'POS Terminals', 'Profit and Loss', 'Cash Balance', 'Daily Sales', 'Cashier Profitability', 'Shop Profitability', 'System Logs', 'Issues', 'Sync Issues', 'Configs', 'Settings', 'Payroll', 'Dashboard', 'Tenants', 'Subscription Plans', 'Payment Providers', 'Support Tickets', 'My Preferences']
        }
        feature_to_cat = {}
        for cat, features in cat_map.items():
            for f in features:
                feature_to_cat[f] = cat
                
        for record in self:
            record.category = feature_to_cat.get(record.feature, 'settings')

    is_read_only = fields.Boolean(string='Read Only', default=False)
    is_full_access = fields.Boolean(string='Full Access', default=True)

    _sql_constraints = [
        ('bo_profile_feature_uniq', 'unique(profile_id, feature)', 'A feature permission already exists for this profile!')
    ]


MODEL_FEATURE_MAP = {
    'account.move': 'Sales Invoices',
    'havanoposdesk.sale': 'Sales Invoices',
    'havanoposdesk.sale.line': 'Sales Invoices',
    'purchase.order': 'Purchases',
    'havanoposdesk.purchase': 'Purchases',
    'havanoposdesk.purchase.line': 'Purchases',
    'res.partner': 'Customers',
    'havanoposdesk.customer': 'Customers',
    'havanoposdesk.supplier': 'Suppliers',
    'havanoposdesk.customer.group': 'Customer Groups',
    'account.tax': 'Taxes',
    'res.currency.rate': 'Exchange Rate',
    'res.currency': 'Currencies',
    'havanoposdesk.store': 'Stores',
    'res.users': 'Users',
    'havanoposdesk.user.rights.profile': 'User Rights Profiles',
    'havanoposdesk.subscription': 'My Subscription',
    'account.account': 'Chart of Accounts',
    'havanoposdesk.stock.transfer': 'Stock Transfers',
    'havanoposdesk.stock.adjustment': 'Stock Adjustments',
    'havanoposdesk.stock.valuation': 'Stock Evaluations',
    'havanoposdesk.stock.ledger': 'Stock Ledger',
    'havanoposdesk.product': 'Products',
    'uom.uom': 'UOM',
    'product.pricelist': 'Pricelists',
    'havanoposdesk.category': 'Categories',
    'havanoposdesk.item.profitability.report': 'Item Profitability',
    'havanoposdesk.category.profitability.report': 'Category Profitability',
    'havanoposdesk.sales.return': 'Sales Returns',
    'havanoposdesk.expense': 'Expense Posting',
    'account.payment': 'Payments',
    'havanoposdesk.payment': 'Payments',
    'havanoposdesk.pos.terminal': 'POS Terminals',
    'havanoposdesk.profit.loss.report': 'Profit and Loss',
    'havanoposdesk.cash.balance': 'Cash Balance',
    'havanoposdesk.daily.sales.report': 'Daily Sales',
    'havanoposdesk.cashier.profitability.report': 'Cashier Profitability',
    'havanoposdesk.shop.profitability.report': 'Shop Profitability',
    'havanoposdesk.system.log': 'System Logs',
    'havanoposdesk.issue': 'Issues',
    'havanoposdesk.sync.issue': 'Sync Issues',
    'havanoposdesk.config': 'Configs',
    'res.config.settings': 'Settings',
    'havanoposdesk.tenant': 'Tenants',
    'havanoposdesk.subscription.plan': 'Subscription Plans',
}

import logging
_logger = logging.getLogger(__name__)

from odoo.models import BaseModel
original_check_access_rights = BaseModel.check_access_rights
original_check_access = BaseModel._check_access

HAVANO_MODELS = frozenset(MODEL_FEATURE_MAP.keys())

from odoo.models import BaseModel, Model, AbstractModel, TransientModel

def custom_check_access(self, operation: str):
    if operation == 'read':
        if self._name in ('res.currency', 'res.currency.rate') or self.env.context.get('bypass_backoffice_read'):
            return None
        if self._name.startswith('havanoposdesk.') or self._name in HAVANO_MODELS:
            user = self.env.user
            if self.env.su or user.id == 1 or getattr(user, 'havano_role', None) == 'super_admin':
                return None
            if not self._ids or 'tenant_id' not in self._fields or not user.tenant_id:
                return None
            try:
                records_tenant_ids = set(self.sudo().mapped('tenant_id.id'))
                if records_tenant_ids.issubset({False, user.tenant_id.id}):
                    return None
            except Exception:
                pass
    return original_check_access(self, operation)

BaseModel._check_access = custom_check_access
Model._check_access = custom_check_access
AbstractModel._check_access = custom_check_access
TransientModel._check_access = custom_check_access

class IrRule(models.Model):
    _inherit = 'ir.rule'

    @api.model
    def _compute_domain(self, model_name, mode='read'):
        if mode == 'read' and self.env.context.get('bypass_backoffice_read'):
            try:
                from odoo.orm.domains import Domain
                return Domain.TRUE
            except ImportError:
                return []
        return super()._compute_domain(model_name, mode=mode)

class IrModelAccess(models.Model):
    _inherit = 'ir.model.access'

    @api.model
    def check(self, model, mode='read', raise_exception=True):
        if self.env.su or self.env.uid == 1:
            return True
        if mode == 'read' and (model in ('res.currency', 'res.currency.rate') or self.env.context.get('bypass_backoffice_read')):
            return True
        if isinstance(model, str) and (model.startswith('havanoposdesk.') or model in HAVANO_MODELS):
            if bool(self.env.uid):
                return True
        return super().check(model, mode=mode, raise_exception=raise_exception)

    @api.model
    @tools.ormcache('self.env.uid', 'mode')
    def _get_allowed_models(self, mode='read'):
        res = super()._get_allowed_models(mode=mode)
        if bool(self.env.uid):
            return res | HAVANO_MODELS | {'res.currency', 'res.currency.rate'}
        if mode == 'read':
            return res | {'res.currency', 'res.currency.rate'}
        return res


def enforce_backoffice_permissions(self, operation, raise_exception=True):
    if not isinstance(operation, str) or operation not in ('read', 'write', 'create', 'unlink'):
        return True

    # 1. Superuser / Admin user id 1 / Super Admin role always have full bypass
    if self.env.su or self.env.user.id == 1:
        return True
    
    if getattr(self.env.user, 'havano_role', None) == 'super_admin':
        return True

    # 2. Currency and exchange rates must always be readable so monetary fields and reports render properly
    if operation == 'read' and self._name in ('res.currency', 'res.currency.rate'):
        return True

    # 3. Context bypass for internal reads / exports
    if operation == 'read' and self.env.context.get('bypass_backoffice_read'):
        return True

    # 4. Check backoffice permissions for custom models
    if self._name in MODEL_FEATURE_MAP:
        user = self.env.user
        profile = user.user_rights_profile_id
        feature_name = MODEL_FEATURE_MAP[self._name]

        # If user has no explicit profile assigned or is Admin, default safely
        if not profile:
            if user.havano_role in ('admin', 'super_admin') or operation == 'read':
                return True
            if raise_exception:
                raise AccessError(f"Permission Denied: No User Rights Profile assigned.")
            return False

        if user.havano_role == 'admin' and not profile:
            return True
            
        bo_perm = profile.backoffice_permission_ids.filtered(lambda p: p.feature == feature_name)
        if not bo_perm:
            if user.havano_role in ('admin', 'super_admin') or operation == 'read':
                return True
            if raise_exception:
                raise AccessError(f"Permission Denied: You do not have access to '{feature_name}'.")
            return False
            
        perm = bo_perm[0]
        if not perm.is_full_access and not perm.is_read_only:
            if operation == 'read' and user.havano_role == 'admin':
                return True
            if raise_exception:
                raise AccessError(f"Permission Denied: You do not have access to '{feature_name}'.")
            return False
            
        if operation in ('write', 'create', 'unlink') and perm.is_read_only:
            if raise_exception:
                raise AccessError(f"Permission Denied: You have Read-Only access to '{feature_name}'. You cannot create, modify, or delete records.")
            return False
                
    return original_check_access_rights(self, operation, raise_exception)

BaseModel.check_access_rights = enforce_backoffice_permissions

original_export_data = BaseModel.export_data

def custom_export_data(self, fields_to_export):
    return original_export_data(self.with_context(bypass_backoffice_read=True), fields_to_export)

BaseModel.export_data = custom_export_data

import xml.etree.ElementTree as ET

class Base(models.AbstractModel):
    _inherit = 'base'

    @api.model
    def get_views(self, views, options=None):
        res = super(Base, self).get_views(views, options=options)
        
        if self._name in MODEL_FEATURE_MAP:
            if not (self.env.su or self.env.user.id == 1 or getattr(self.env.user, 'havano_role', None) == 'super_admin'):
                user = self.env.user
                profile = user.user_rights_profile_id
                feature_name = MODEL_FEATURE_MAP[self._name]
                
                if profile:
                    bo_perm = profile.backoffice_permission_ids.filtered(lambda p: p.feature == feature_name)
                    if bo_perm and bo_perm[0].is_read_only:
                        for v_type, view_data in res.get('views', {}).items():
                            if 'arch' in view_data:
                                try:
                                    arch_node = ET.fromstring(view_data['arch'])
                                    arch_node.set('create', '0')
                                    arch_node.set('edit', '0')
                                    arch_node.set('delete', '0')
                                    view_data['arch'] = ET.tostring(arch_node, encoding='unicode')
                                except Exception as e:
                                    _logger.error("Failed to inject read-only attributes into view: %s", e)
                                    
        return res
