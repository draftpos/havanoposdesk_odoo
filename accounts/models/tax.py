from odoo import models, fields, api

class HavanoposdeskTax(models.Model):
    _name = 'havanoposdesk.tax'
    _description = 'Tax Configuration'

    name = fields.Char(string='Tax Code', required=True)
    tax_type = fields.Selection([
        ('Sales', 'Sales'),
        ('Purchases', 'Purchases')
    ], string='Tax Type', required=True, default='Sales')
    rate = fields.Float(string='Rate (%)', required=True, default=0.0)
    is_inclusive = fields.Boolean(string='Tax Included in Price', default=False)
    active = fields.Boolean(string='Active', default=False)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )

    @api.depends('name', 'rate')
    def _compute_display_name(self):
        for record in self:
            record.display_name = f"{record.name} ({record.rate}%)"
