from odoo import models, fields, api

class Account(models.Model):
    _name = 'havanoposdesk.account'
    _description = 'Account'
    
    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Account name must be unique per tenant!')
    ]

    name = fields.Char(string='Account Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    type = fields.Selection([
        ('Cash', 'Cash'),
        ('Bank', 'Bank'),
        ('Expense', 'Expense')
    ], string='Account Type', required=True)
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='Currency used for this Cash or Bank account.',
        default=lambda self: self.env.user.tenant_id.currency_id.id or self.env.ref('base.USD', raise_if_not_found=False).id
    )
    balance = fields.Float(string='Balance', default=0.0)
    
    # Store reference for multi-tenancy if applicable
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store')
    store_ids = fields.Many2many(
        'havanoposdesk.store',
        string='Stores',
        default=lambda self: [self.env.user.default_store_id.id] if self.env.user.default_store_id else ([self.env.user.store_ids[0].id] if self.env.user.store_ids else [])
    )

    def action_activate(self):
        self.write({'active': True})

    def action_deactivate(self):
        self.write({'active': False})

    def action_toggle_active(self):
        for record in self:
            record.active = not record.active

