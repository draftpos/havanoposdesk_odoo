from odoo import models, fields

class Supplier(models.Model):
    _name = 'havanoposdesk.supplier'
    _description = 'Supplier'

    name = fields.Char(string='Supplier Name', required=True)
    supplier_type = fields.Selection([
        ('company', 'Company'),
        ('individual', 'Individual'),
        ('partnership', 'Partnership')
    ], string='Supplier Type', default='company', required=True)
