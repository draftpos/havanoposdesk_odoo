from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class Payment(models.Model):
    _name = 'havanoposdesk.payment'
    _description = 'Payment'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        required=True,
        default=lambda self: self.env.user.tenant_id.currency_id.id or self.env.ref('base.USD', raise_if_not_found=False).id
    )
    exchange_rate = fields.Float(string='Exchange Rate', default=1.0, digits=(12, 6))
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    amount_base = fields.Float(string='Base Amount', compute='_compute_amount_base', store=True)

    @api.onchange('currency_id', 'tenant_id')
    def _onchange_currency_id(self):
        if self.currency_id and self.tenant_id and self.tenant_id.currency_id:
            if self.currency_id == self.tenant_id.currency_id:
                self.exchange_rate = 1.0
            else:
                date = self.date or fields.Date.context_today(self)
                rate = self.currency_id._get_conversion_rate(self.tenant_id.currency_id, self.currency_id, self.env.company, date)
                self.exchange_rate = rate or 1.0
    
    payment_type = fields.Selection([
        ('receipt', 'Receive Money'),
        ('payment', 'Send Money')
    ], string='Payment Type', required=True, default='receipt')
    
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Supplier')
    ], string='Partner Type', required=True, default='customer')
    
    customer_id = fields.Many2one('havanoposdesk.customer', string='Customer')
    customer_balance = fields.Float(related='customer_id.balance', string='Customer Balance')
    customer_secondary_balance = fields.Float(related='customer_id.secondary_balance', string='Secondary Balance')
    customer_allow_multi_currency = fields.Boolean(related='customer_id.allow_multi_currency', string='Customer Multi Currency')
    customer_secondary_currency_id = fields.Many2one('res.currency', related='customer_id.secondary_currency_id')
    
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier')
    supplier_balance = fields.Float(related='supplier_id.balance', string='Supplier Balance')
    supplier_secondary_balance = fields.Float(related='supplier_id.secondary_balance', string='Secondary Balance')
    supplier_allow_multi_currency = fields.Boolean(related='supplier_id.allow_multi_currency', string='Supplier Multi Currency')
    supplier_secondary_currency_id = fields.Many2one('res.currency', related='supplier_id.secondary_currency_id')
    
    account_id = fields.Many2one('havanoposdesk.account', string='Bank/Cash Account', required=True, domain="[('type', 'in', ['Bank', 'Cash'])]")
    
    amount = fields.Float(string='Amount', required=True, default=0.0)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    reference = fields.Char(string='Memo / Reference')
    pos_sale_ids = fields.One2many('havanoposdesk.sale', 'pos_payment_id', string='POS Sales Breakdown')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))
            
            if vals.get('name', 'New') == 'New':
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    if vals.get('payment_type') == 'payment':
                        vals['name'] = tenant._get_next_sequence('pay_out')
                    else:
                        vals['name'] = tenant._get_next_sequence('pay_in')
                else:
                    if vals.get('payment_type') == 'payment':
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.payment.out') or 'PAY/New'
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.payment.in') or 'REC/New'
        return super().create(vals_list)

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft' and not self.env.context.get('bypass_payment_check') and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted payment. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed/posted payment. Please cancel it first.")
        return super().unlink()

    @api.depends('amount', 'exchange_rate')
    def _compute_amount_base(self):
        for record in self:
            if record.exchange_rate and record.exchange_rate != 0:
                record.amount_base = record.amount / record.exchange_rate
            else:
                record.amount_base = record.amount

    def action_post(self):
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be posted.")
            if payment.amount <= 0:
                raise UserError("Payment amount must be greater than zero.")
                
            # Determine the amount in the account's currency
            account_currency = payment.account_id.currency_id or payment.tenant_id.currency_id
            if account_currency == payment.currency_id:
                account_amount = payment.amount
            elif account_currency == payment.tenant_id.currency_id:
                account_amount = payment.amount_base
            else:
                date = payment.date or fields.Date.context_today(payment)
                rate = payment.tenant_id.currency_id._get_conversion_rate(
                    payment.tenant_id.currency_id, account_currency, payment.env.company, date
                )
                account_amount = payment.amount_base * rate
                
            # Update Account Balance using sudo()
            if payment.payment_type == 'receipt':
                payment.account_id.sudo().balance += account_amount
            else:
                payment.account_id.sudo().balance -= account_amount
                
            payment.write({'state': 'posted'})

    def action_cancel(self):
        for payment in self:
            if payment.state != 'posted':
                payment.write({'state': 'cancelled'})
                continue
                
            # Determine the amount in the account's currency
            account_currency = payment.account_id.currency_id or payment.tenant_id.currency_id
            if account_currency == payment.currency_id:
                account_amount = payment.amount
            elif account_currency == payment.tenant_id.currency_id:
                account_amount = payment.amount_base
            else:
                date = payment.date or fields.Date.context_today(payment)
                rate = payment.tenant_id.currency_id._get_conversion_rate(
                    payment.tenant_id.currency_id, account_currency, payment.env.company, date
                )
                account_amount = payment.amount_base * rate
                
            # Reverse Account Balance using sudo()
            if payment.payment_type == 'receipt':
                payment.account_id.sudo().balance -= account_amount
            else:
                payment.account_id.sudo().balance += account_amount
                
            payment.write({'state': 'cancelled'})

    def action_draft(self):
        for payment in self:
            if payment.state == 'cancelled':
                payment.write({'state': 'draft'})
