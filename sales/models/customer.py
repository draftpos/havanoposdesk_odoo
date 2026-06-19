from odoo import models, fields, api

class CustomerGroup(models.Model):
    _name = 'havanoposdesk.customer.group'
    _description = 'Customer Group'

    name = fields.Char(string='Group Name', required=True)

class Customer(models.Model):
    _name = 'havanoposdesk.customer'
    _description = 'Customer'

    name = fields.Char(string='Customer Name', required=True)
    phone = fields.Char(string='Phone')
    address = fields.Char(string='Address')
    city = fields.Char(string='City')
    country = fields.Char(string='Country')
    customer_group_id = fields.Many2one('havanoposdesk.customer.group', string='Customer Group')
    
    sale_ids = fields.One2many('havanoposdesk.sale', 'customer', string='Sales')
    balance = fields.Float(string='Balance', compute='_compute_balance', store=False)

    @api.depends('sale_ids.amount_total')
    def _compute_balance(self):
        for record in self:
            record.balance = sum(record.sale_ids.mapped('amount_total'))

    customer_type = fields.Selection([
        ('company', 'Company'),
        ('individual', 'Individual'),
        ('partnership', 'Partnership')
    ], string='Customer Type', default='individual', required=True)
