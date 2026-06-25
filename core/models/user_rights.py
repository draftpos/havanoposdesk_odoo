from odoo import models, fields, api

class HavanoposdeskUserRightsProfile(models.Model):
    _name = 'havanoposdesk.user.rights.profile'
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
    permission_ids = fields.One2many(
        'havanoposdesk.user.rights.permission', 
        'profile_id', 
        string='Permissions', 
        copy=True
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Force tenant_id from context if not specified
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
            
            # Default pre-populate all 10 features if permissions not specified
            if 'permission_ids' not in vals or not vals['permission_ids']:
                features = [
                    'Dashboard', 'POS', 'Quotations', 'Sales', 'Products',
                    'Stock Management', 'Payment Entries', 'Reports', 'Settings', 'Printer'
                ]
                permission_lines = []
                for feature in features:
                    permission_lines.append((0, 0, {
                        'feature': feature,
                        'can_read': True,
                        'can_create': True,
                        'can_update': True,
                        'can_delete': True,
                        'can_submit': True,
                    }))
                vals['permission_ids'] = permission_lines
        return super().create(vals_list)

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
        ('Stock Management', 'Stock Management'),
        ('Payment Entries', 'Payment Entries'),
        ('Reports', 'Reports'),
        ('Settings', 'Settings'),
        ('Printer', 'Printer')
    ], string='Feature', required=True)
    can_read = fields.Boolean(string='Read', default=True)
    can_create = fields.Boolean(string='Create', default=True)
    can_update = fields.Boolean(string='Update', default=True)
    can_delete = fields.Boolean(string='Delete', default=True)
    can_submit = fields.Boolean(string='Submit', default=True)

    _sql_constraints = [
        ('profile_feature_uniq', 'unique(profile_id, feature)', 'A feature permission already exists for this profile!')
    ]
