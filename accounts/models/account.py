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
    
    # Store reference for multi-tenancy if applicable
    store_id = fields.Many2one('havanoposdesk.store', string='Store')
