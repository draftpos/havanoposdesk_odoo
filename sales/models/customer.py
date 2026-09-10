from odoo import models, fields, api

class CustomerGroup(models.Model):
    _name = 'havanoposdesk.customer.group'
    _description = 'Customer'

    _constraints = [
        models.Constraint('unique (name, tenant_id)', 'Customer name must be unique per tenant!')
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
    tenant_allow_multi_currency = fields.Boolean(related='tenant_id.allow_multi_currency', store=False)
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        default=lambda self: self.env.user.tenant_id.currency_id.id or self.env.ref('base.USD', raise_if_not_found=False).id
    )

    def _default_country_id(self):
        return self.env['res.country'].search([('name', '=', 'Zimbabwe')], limit=1).id

    def _default_customer_group_id(self):
        tenant_id = self.env.user.tenant_id.id if self.env.user.tenant_id else False
        domain = [('tenant_id', '=', tenant_id)] if tenant_id else []
        return self.env['havanoposdesk.customer.group'].search(domain, limit=1).id

    def _default_store_ids(self):
        store = self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1)
        if not store and self.env.user.tenant_id:
            store = self.env['havanoposdesk.store'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1)
        return [(6, 0, [store.id])] if store else []

    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    address = fields.Char(string='Address')
    city = fields.Char(string='City')
    country_id = fields.Many2one('res.country', string='Country', default=_default_country_id)
    customer_group_id = fields.Many2one('havanoposdesk.customer.group', string='Customer Group', default=_default_customer_group_id)
    tin = fields.Char(string='TIN')
    vat = fields.Char(string='VAT')

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
    store_ids = fields.Many2many('havanoposdesk.store', string='Stores', default=_default_store_ids)



    @api.depends('sale_ids.amount_total_base', 'sale_ids.is_return', 'sale_ids.payment_status', 'sale_ids.state', 'payment_ids.amount_base', 'payment_ids.payment_type', 'payment_ids.state')
    def _compute_balance(self):
        for record in self:
            valid_sales = record.sale_ids.filtered(lambda s: s.state in ['confirmed', 'done'])
            total_sales = sum(valid_sales.mapped('amount_total_base'))
            
            posted_payments = record.payment_ids.filtered(lambda p: p.state == 'posted')
            receipts = sum(posted_payments.filtered(lambda p: p.payment_type == 'receipt').mapped('amount_base'))
            refunds = sum(posted_payments.filtered(lambda p: p.payment_type == 'payment').mapped('amount_base'))
            
            record.balance = total_sales - receipts + refunds

