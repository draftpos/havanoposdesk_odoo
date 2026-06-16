from odoo import models, fields

class HavanoposdeskUom(models.Model):
    _name = 'havanoposdesk.uom'
    _description = 'Unit of Measure'

    name = fields.Char(string='UOM Name', required=True)
    abbreviation = fields.Char(string='Abbreviation')
    weight_scale_status = fields.Boolean(string='Weight Scale Status', default=False)
    measurement_conversion = fields.Boolean(string='Measurement Conversion', default=False)
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env['havanoposdesk.tenant'].search([], limit=1).id)
