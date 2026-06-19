from odoo import models, fields

class Account(models.Model):
    _name = 'havanoposdesk.account'
    _description = 'Account'

    name = fields.Char(string='Account Name', required=True)
    type = fields.Selection([
        ('Cash', 'Cash'),
        ('Bank', 'Bank'),
        ('Expense', 'Expense')
    ], string='Account Type', required=True, default='Expense')
    balance = fields.Float(string='Balance', default=0.0)
    
    # Store reference for multi-tenancy if applicable
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store')
