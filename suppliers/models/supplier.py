from odoo import models, fields, api
from odoo.exceptions import ValidationError

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
    
    tenant_allow_multi_currency = fields.Boolean(related='tenant_id.allow_multi_currency', store=False)
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        default=lambda self: self.env.user.tenant_id.currency_id.id or self.env.ref('base.USD', raise_if_not_found=False).id
    )
    allow_multi_currency = fields.Boolean(string='Allow Multi Currency', default=False)
    secondary_currency_id = fields.Many2one('res.currency', string='Secondary Currency')
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    
    @api.constrains('currency_id', 'secondary_currency_id')
    def _check_currencies(self):
        for record in self:
            self.env['res.currency']._validate_tenant_currency(record.currency_id, record.tenant_id)
            self.env['res.currency']._validate_tenant_currency(record.secondary_currency_id, record.tenant_id)
            if record.allow_multi_currency and record.currency_id and record.secondary_currency_id:
                if record.currency_id == record.secondary_currency_id:
                    raise ValidationError("The primary and secondary currencies cannot be the same.")
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
    secondary_balance = fields.Float(string='Secondary Balance', compute='_compute_secondary_balance', store=False)

    @api.depends('balance', 'secondary_currency_id', 'allow_multi_currency')
    def _compute_secondary_balance(self):
        for record in self:
            if record.allow_multi_currency and record.secondary_currency_id and record.tenant_currency_id:
                rate = record.tenant_currency_id._get_conversion_rate(
                    record.tenant_currency_id, record.secondary_currency_id, self.env.company, fields.Date.context_today(record)
                )
                record.secondary_balance = record.balance * rate
            else:
                record.secondary_balance = 0.0

    @api.depends('purchase_ids.amount_total_base', 'payment_ids.amount_base', 'payment_ids.payment_type', 'payment_ids.state')
    def _compute_balance(self):
        for record in self:
            total_purchases = sum(record.purchase_ids.mapped('amount_total_base'))
            
            posted_payments = record.payment_ids.filtered(lambda p: p.state == 'posted')
            payments = sum(posted_payments.filtered(lambda p: p.payment_type == 'payment').mapped('amount_base'))
            refunds = sum(posted_payments.filtered(lambda p: p.payment_type == 'receipt').mapped('amount_base'))
            
            record.balance = total_purchases - payments + refunds
