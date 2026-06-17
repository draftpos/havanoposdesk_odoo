from odoo import models, fields

class Supplier(models.Model):
    _name = 'havanoposdesk.supplier'
    _description = 'Supplier'

    name = fields.Char(string='Supplier Name', required=True)
    address = fields.Char(string='Address')
    phone = fields.Char(string='Phone Number')
    email = fields.Char(string='Email')
