from odoo import models, fields, api

class CustomerGroup(models.Model):
    _name = 'havanoposdesk.customer.group'
    _description = 'Customer'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Customer name must be unique per tenant!')
    ]

    name = fields.Char(string='Group Name', required=True)
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )

    @api.depends('name', 'tenant_id')
    def _compute_display_name(self):
        is_super_admin = self.env.user.has_group('base.group_system')
        for record in self:
            if is_super_admin and record.tenant_id:
                record.display_name = f"{record.name} ({record.tenant_id.name})"
            else:
                record.display_name = record.name

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
    currency_id = fields.Many2one(related='store_id.currency_id', string='Currency', store=False)
    phone = fields.Char(string='Phone')
    address = fields.Char(string='Address')
    city = fields.Char(string='City')
    country_id = fields.Many2one('res.country', string='Country')
    customer_group_id = fields.Many2one('havanoposdesk.customer.group', string='Customer Group')
    tin = fields.Char(string='TIN')
    vat = fields.Char(string='VAT')
    customer_type = fields.Selection([
        ('individual', 'Individual'),
        ('company', 'Company')
    ], string='Customer Type', default='individual')

    @api.depends('name', 'tenant_id')
    def _compute_display_name(self):
        is_super_admin = self.env.user.has_group('base.group_system')
        for record in self:
            if is_super_admin and record.tenant_id:
                record.display_name = f"{record.name} ({record.tenant_id.name})"
            else:
                record.display_name = record.name
    
    sale_ids = fields.One2many('havanoposdesk.sale', 'customer', string='Sales')
    payment_ids = fields.One2many('havanoposdesk.payment', 'customer_id', string='Payments')
    balance = fields.Float(string='Balance', compute='_compute_balance', store=False)
    store_id = fields.Many2one('havanoposdesk.store', string='Store')

    @api.depends('sale_ids.amount_total', 'sale_ids.is_return', 'sale_ids.payment_status', 'payment_ids.amount', 'payment_ids.payment_type', 'payment_ids.state')
    def _compute_balance(self):
        for record in self:
            account_sales = record.sale_ids.filtered(lambda s: s.payment_status == 'account')
            total_sales = sum(account_sales.mapped('amount_total'))
            
            posted_payments = record.payment_ids.filtered(lambda p: p.state == 'posted')
            receipts = sum(posted_payments.filtered(lambda p: p.payment_type == 'receipt').mapped('amount'))
            refunds = sum(posted_payments.filtered(lambda p: p.payment_type == 'payment').mapped('amount'))
            
            record.balance = total_sales - receipts + refunds

