from odoo import models, fields, api, _

class RestaurantFloor(models.Model):
    _name = 'havanoposdesk.restaurant.floor'
    _description = 'Restaurant Floor'
    _order = 'sequence, id'

    name = fields.Char(string='Floor Name', required=True)
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(default=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        ondelete='cascade',
        default=lambda self: self.env.user.tenant_id.id if hasattr(self.env.user, 'tenant_id') else False
    )

    table_ids = fields.One2many('havanoposdesk.restaurant.table', 'floor_id', string='Tables')


class RestaurantTable(models.Model):
    _name = 'havanoposdesk.restaurant.table'
    _description = 'Restaurant Table'
    _order = 'name'

    name = fields.Char(string='Table Name', required=True)
    seats = fields.Integer(string='Seats', default=1)
    active = fields.Boolean(default=True)
    floor_id = fields.Many2one('havanoposdesk.restaurant.floor', string='Floor', required=True, ondelete='cascade')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        ondelete='cascade',
        default=lambda self: self.env.user.tenant_id.id if hasattr(self.env.user, 'tenant_id') else False
    )


class RestaurantWaiter(models.Model):
    _name = 'havanoposdesk.restaurant.waiter'
    _description = 'Restaurant Waiter'
    _order = 'name'

    name = fields.Char(string='Waiter Name', required=True)
    pin = fields.Char(string='PIN', help='Optional PIN for the waiter to login')
    active = fields.Boolean(default=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        ondelete='cascade',
        default=lambda self: self.env.user.tenant_id.id if hasattr(self.env.user, 'tenant_id') else False
    )
