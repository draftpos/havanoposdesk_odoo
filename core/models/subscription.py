from odoo import models, fields, api
from odoo.exceptions import UserError

class HavanoposdeskSubscriptionPlan(models.Model):
    _name = 'havanoposdesk.subscription.plan'
    _description = 'Subscription Plan for SaaS'

    name = fields.Char(string='Plan Name', required=True)
    price = fields.Float(string='Price')
    duration_days = fields.Integer(string='Duration (Days)', default=30)
    max_stores = fields.Integer(string='Maximum Stores', default=0)  # 0 = unlimited
    max_users = fields.Integer(string='Maximum Users (Cashiers)', default=0)
    max_terminals = fields.Integer(string='Maximum POS Terminals', default=0)

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.user.havano_role != 'super_admin' and not self.env.su:
            raise UserError('Only Super Admins can create subscription plans.')
        return super().create(vals_list)

    def write(self, vals):
        if self.env.user.havano_role != 'super_admin' and not self.env.su:
            raise UserError('Only Super Admins can modify subscription plans.')
        return super().write(vals)

    def unlink(self):
        if self.env.user.havano_role != 'super_admin' and not self.env.su:
            raise UserError('Only Super Admins can delete subscription plans.')
        return super().unlink()


