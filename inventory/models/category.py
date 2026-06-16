from odoo import models, fields

class HavanoposdeskCategory(models.Model):
    _name = 'havanoposdesk.category'
    _description = 'Product Category'

    name = fields.Char(string='Category Name', required=True)
    is_main_category = fields.Boolean(string='Is Main Category', default=True)
    parent_id = fields.Many2one('havanoposdesk.category', string='Parent Category')
    classification_code = fields.Char(string='Classification Code')
    image_1920 = fields.Image(string='Image', max_width=1920, max_height=1920)
    color_hex = fields.Char(string='Color Hex')
    
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, default=lambda self: self.env['havanoposdesk.tenant'].search([], limit=1).id)
