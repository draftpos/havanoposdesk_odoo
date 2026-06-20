from odoo import models, fields, api

class CustomerGroup(models.Model):
    _name = 'havanoposdesk.customer.group'
    _description = 'Customer Group'

    name = fields.Char(string='Group Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )

class Customer(models.Model):
    _name = 'havanoposdesk.customer'
    _description = 'Customer'

    name = fields.Char(string='Customer Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    phone = fields.Char(string='Phone')
    address = fields.Char(string='Address')
    city = fields.Char(string='City')
    country_id = fields.Many2one('res.country', string='Country')
    customer_group_id = fields.Many2one('havanoposdesk.customer.group', string='Customer Group')
    
    sale_ids = fields.One2many('havanoposdesk.sale', 'customer', string='Sales')
    payment_ids = fields.One2many('havanoposdesk.payment', 'customer_id', string='Payments')
    balance = fields.Float(string='Balance', compute='_compute_balance', store=False)

    @api.depends('sale_ids.amount_total', 'sale_ids.is_return', 'payment_ids.amount', 'payment_ids.payment_type', 'payment_ids.state')
    def _compute_balance(self):
        for record in self:
            normal_sales = sum(record.sale_ids.filtered(lambda s: not s.is_return).mapped('amount_total'))
            return_sales = sum(record.sale_ids.filtered(lambda s: s.is_return).mapped('amount_total'))
            total_sales = normal_sales - return_sales
            
            posted_payments = record.payment_ids.filtered(lambda p: p.state == 'posted')
            receipts = sum(posted_payments.filtered(lambda p: p.payment_type == 'receipt').mapped('amount'))
            refunds = sum(posted_payments.filtered(lambda p: p.payment_type == 'payment').mapped('amount'))
            
            record.balance = total_sales - receipts + refunds

    customer_type = fields.Selection([
        ('company', 'Company'),
        ('individual', 'Individual'),
        ('partnership', 'Partnership')
    ], string='Customer Type', default='individual', required=True)
