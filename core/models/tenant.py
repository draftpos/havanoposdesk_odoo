from odoo import models, fields

class HavanoposdeskTenant(models.Model):
    _name = 'havanoposdesk.tenant'
    _description = 'Havano POS Desk Tenant'

    name = fields.Char(string='Tenant Name', required=True)
    active = fields.Boolean(default=True)
