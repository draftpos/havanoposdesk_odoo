from odoo import models, fields

class Customer(models.Model):
    _name = 'havanoposdesk.customer'
    _description = 'Customer'

    name = fields.Char(string='Customer Name', required=True)
    address = fields.Char(string='Address')
    phone = fields.Char(string='Phone Number')
    email = fields.Char(string='Email')
