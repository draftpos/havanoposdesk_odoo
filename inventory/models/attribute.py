from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class HavanoposdeskAttribute(models.Model):
    _name = 'havanoposdesk.attribute'
    _description = 'Variant Attribute'
    _order = 'sequence, name'

    name = fields.Char(string='Attribute Name', required=True, index=True, help="e.g. Size, Color, Shoe Size, Material")
    active = fields.Boolean(string='Active', default=True, help="Toggle to activate or deactivate this attribute.")
    sequence = fields.Integer(string='Sequence', default=10)
    value_ids = fields.One2many('havanoposdesk.attribute.value', 'attribute_id', string='Attribute Values', copy=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, index=True, default=lambda self: self.env.user.tenant_id)
    value_count = fields.Integer(string='Values Count', compute='_compute_value_count')

    @api.depends('value_ids')
    def _compute_value_count(self):
        for rec in self:
            rec.value_count = len(rec.value_ids)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id'):
                vals['tenant_id'] = self.env.user.tenant_id.id
        records = super().create(vals_list)
        for rec in records:
            # Propagate tenant_id to children values
            for val in rec.value_ids:
                if not val.tenant_id:
                    val.tenant_id = rec.tenant_id.id
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'tenant_id' in vals:
            for rec in self:
                rec.value_ids.write({'tenant_id': vals['tenant_id']})
        return res


class HavanoposdeskAttributeValue(models.Model):
    _name = 'havanoposdesk.attribute.value'
    _description = 'Variant Attribute Value'
    _order = 'attribute_id, sequence, id'

    attribute_id = fields.Many2one('havanoposdesk.attribute', string='Attribute', required=True, ondelete='cascade', index=True)
    name = fields.Char(string='Value', required=True, help="e.g. Small, Medium, Large, or 5, 6, 7, 8, etc.")
    sequence = fields.Integer(string='Sequence', default=10)
    color = fields.Integer(string='Color Index', default=0)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, index=True, default=lambda self: self.env.user.tenant_id)
    display_name = fields.Char(string='Display Name', compute='_compute_display_name', store=True)

    @api.depends('attribute_id.name', 'name')
    def _compute_display_name(self):
        for rec in self:
            if rec.attribute_id and rec.attribute_id.name:
                rec.display_name = f"{rec.attribute_id.name}: {rec.name}"
            else:
                rec.display_name = rec.name or ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id'):
                attr = self.env['havanoposdesk.attribute'].browse(vals.get('attribute_id'))
                if attr and attr.tenant_id:
                    vals['tenant_id'] = attr.tenant_id.id
                else:
                    vals['tenant_id'] = self.env.user.tenant_id.id
        return super().create(vals_list)
