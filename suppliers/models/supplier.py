from odoo import models, fields, api

class HavanoposdeskSupplier(models.Model):
    _name = 'havanoposdesk.supplier'
    _description = 'Supplier'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Supplier name must be unique per tenant!')
    ]

    name = fields.Char(string='Supplier Name', required=True)
    phone = fields.Char(string='Phone')
    email = fields.Char(string='Email')
    address = fields.Text(string='Address')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one(
        'havanoposdesk.store', 
        string='Store', 
        required=True, 
        default=lambda self: self.env.user.default_store_id.id or self.env['havanoposdesk.store'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1).id
    )

    @api.depends('name', 'tenant_id')
    def _compute_display_name(self):
        is_super_admin = self.env.user.has_group('base.group_system')
        for record in self:
            if is_super_admin and record.tenant_id:
                record.display_name = f"{record.name} ({record.tenant_id.name})"
            else:
                record.display_name = record.name

    purchase_ids = fields.One2many('havanoposdesk.purchase', 'supplier', string='Purchases')
    payment_ids = fields.One2many('havanoposdesk.payment', 'supplier_id', string='Payments')
    balance = fields.Float(string='Balance', compute='_compute_balance', store=False)

    @api.depends('purchase_ids.amount_total', 'payment_ids.amount', 'payment_ids.payment_type', 'payment_ids.state')
    def _compute_balance(self):
        for record in self:
            total_purchases = sum(record.purchase_ids.mapped('amount_total'))
            
            posted_payments = record.payment_ids.filtered(lambda p: p.state == 'posted')
            payments = sum(posted_payments.filtered(lambda p: p.payment_type == 'payment').mapped('amount'))
            refunds = sum(posted_payments.filtered(lambda p: p.payment_type == 'receipt').mapped('amount'))
            
            record.balance = total_purchases - payments + refunds
