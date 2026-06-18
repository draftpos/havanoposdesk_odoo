from odoo import models, fields

class HavanoposdeskUom(models.Model):
    _name = 'havanoposdesk.uom'
    _description = 'UOM'

    name = fields.Char(string='UOM Name', required=True)
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id)
