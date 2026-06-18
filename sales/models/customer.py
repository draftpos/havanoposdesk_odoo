from odoo import models, fields

class Customer(models.Model):
    _name = 'havanoposdesk.customer'
    _description = 'Customer'

    name = fields.Char(string='Customer Name', required=True)
    customer_type = fields.Selection([
        ('company', 'Company'),
        ('individual', 'Individual'),
        ('partnership', 'Partnership')
    ], string='Customer Type', default='individual', required=True)
