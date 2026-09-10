from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class Payment(models.Model):
    _name = 'havanoposdesk.payment'
    _inherit = ['havanoposdesk.audit.mixin']
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
        domain="[('tenant_id', '=', tenant_id)]",
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else False
    )
    exchange_rate = fields.Float(string='Exchange Rate', default=1.0, digits=(12, 6))
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')

    @api.constrains('tenant_id', 'currency_id')
    def _check_currency_belongs_to_tenant(self):
        for payment in self:
            self.env['res.currency']._validate_tenant_currency(payment.currency_id, payment.tenant_id)
    amount_base = fields.Float(string='Base Amount', compute='_compute_amount_base', store=True)
    amount_owing_base = fields.Float(string='Owing (Base)', compute='_compute_amount_owing', store=True)
    amount_owing_currency = fields.Float(string='Balance Due', compute='_compute_amount_owing', store=True)

    @api.depends(
        'sale_id.amount_balance', 'sale_id.amount_balance_base', 'sale_id.currency_id',
        'exchange_rate', 'currency_id', 'tenant_currency_id'
    )
    def _compute_amount_owing(self):
        for record in self:
            sale = record.sale_id
            owing_base = sale.amount_balance_base if sale else 0.0
            record.amount_owing_base = owing_base
            if sale and record.currency_id and sale.currency_id and record.currency_id == sale.currency_id:
                record.amount_owing_currency = sale.amount_balance
            else:
                rate = record.exchange_rate if record.exchange_rate and record.exchange_rate != 0 else 1.0
                record.amount_owing_currency = owing_base * rate

    @api.onchange('currency_id', 'tenant_id')
    def _onchange_currency_id(self):
        if self.currency_id and self.tenant_id and self.tenant_id.currency_id:
            if self.currency_id == self.tenant_id.currency_id:
                self.exchange_rate = 1.0
            else:
                date = self.date or fields.Date.context_today(self)
                rate = self.currency_id._get_conversion_rate(self.tenant_id.currency_id, self.currency_id, self.env.company, date)
                self.exchange_rate = rate or 1.0

    @api.onchange('account_id')
    def _onchange_account_id(self):
        """Auto-populate currency from the selected deposit account.

        When a bank/cash account is chosen and it carries an explicit
        currency, we copy that currency to the payment and immediately
        re-trigger the exchange-rate lookup so the rate is also filled in
        without the user having to touch the Currency field manually.
        """
        if self.account_id and self.account_id.currency_id:
            self.currency_id = self.account_id.currency_id
            self._onchange_currency_id()
    
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

    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier')
    supplier_balance = fields.Float(related='supplier_id.balance', string='Supplier Balance')
    supplier_secondary_balance = fields.Float(related='supplier_id.secondary_balance', string='Secondary Balance')
    supplier_allow_multi_currency = fields.Boolean(related='supplier_id.allow_multi_currency', string='Supplier Multi Currency')
    supplier_secondary_currency_id = fields.Many2one('res.currency', related='supplier_id.secondary_currency_id')
    
    is_multi_currency = fields.Boolean(string='Multi-currencies on payment', default=False)
    payment_line_ids = fields.One2many('havanoposdesk.payment.line', 'payment_id', string='Payment Breakdown')
    account_id = fields.Many2one('havanoposdesk.account', string='Bank/Cash Account', domain="[('tenant_id', '=', tenant_id), ('type', 'in', ['Bank', 'Cash']), ('active', '=', True), ('is_on_account', '=', False)]")
    

    amount = fields.Float(string='Amount', required=True, default=0.0, compute='_compute_amount', store=True, readonly=False)
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    reference = fields.Char(string='Memo / Reference')
    pos_sale_ids = fields.One2many('havanoposdesk.sale', 'pos_payment_id', string='POS Sales Breakdown')
    sale_id = fields.Many2one('havanoposdesk.sale', string='Sale Invoice')
    store_id = fields.Many2one('havanoposdesk.store', string='Store / Branch')
    shift_id = fields.Many2one('havanoposdesk.shift', string='Shift')
    transaction_category = fields.Selection([
        ('customer_receipt', 'Customer Receipt'),
        ('supplier_payment', 'Supplier Payment'),
        ('sale', 'POS Sale'),
        ('expense', 'Expense Payout'),
        ('transfer_in', 'Cash Transfer In'),
        ('transfer_out', 'Cash Transfer Out'),
        ('other', 'Other')
    ], string='Transaction Category', default='customer_receipt')
    expense_id = fields.Many2one('havanoposdesk.expense', string='Related Expense')
    transfer_id = fields.Many2one('havanoposdesk.cash.transfer', string='Related Cash Transfer')
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('cancelled', 'Cancelled')
    ], string='Status', required=True, default='draft')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id')
            if not tenant_id and self.env.user.tenant_id:
                tenant_id = self.env.user.tenant_id.id
            if not tenant_id and vals.get('account_id'):
                account = self.env['havanoposdesk.account'].browse(vals.get('account_id'))
                if account.tenant_id:
                    tenant_id = account.tenant_id.id
            if not tenant_id and vals.get('sale_id'):
                sale = self.env['havanoposdesk.sale'].browse(vals.get('sale_id'))
                if sale.tenant_id:
                    tenant_id = sale.tenant_id.id
            if not tenant_id and vals.get('customer_id'):
                cust = self.env['havanoposdesk.customer'].browse(vals.get('customer_id'))
                if cust.tenant_id:
                    tenant_id = cust.tenant_id.id
            if not tenant_id and vals.get('supplier_id'):
                supp = self.env['havanoposdesk.supplier'].browse(vals.get('supplier_id'))
                if supp.tenant_id:
                    tenant_id = supp.tenant_id.id

            if not vals.get('shift_id'):
                if vals.get('sale_id'):
                    sale = self.env['havanoposdesk.sale'].browse(vals.get('sale_id'))
                    if sale.shift_id:
                        vals['shift_id'] = sale.shift_id.id
                if not vals.get('shift_id'):
                    shift_domain = [('user_id', '=', self.env.user.id), ('state', '=', 'open')]
                    if tenant_id:
                        shift_domain.append(('tenant_id', '=', tenant_id))
                    open_shift = self.env['havanoposdesk.shift'].search(shift_domain, limit=1)
                    if open_shift:
                        vals['shift_id'] = open_shift.id

            if tenant_id:
                vals['tenant_id'] = tenant_id
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
            if tenant.currency_id and not vals.get('currency_id'):
                vals['currency_id'] = tenant.currency_id.id
            if vals.get('currency_id'):
                self.env['res.currency']._validate_tenant_currency(vals['currency_id'], tenant)
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
            tenant = self.env['havanoposdesk.tenant'].browse(vals.get('tenant_id', record.tenant_id.id))
            if 'currency_id' in vals:
                self.env['res.currency']._validate_tenant_currency(vals['currency_id'], tenant)
            elif 'tenant_id' in vals:
                self.env['res.currency']._validate_tenant_currency(record.currency_id, tenant)
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

    @api.depends('payment_line_ids.amount_base', 'is_multi_currency', 'exchange_rate')
    def _compute_amount(self):
        for record in self:
            if record.is_multi_currency:
                total_base = sum(record.payment_line_ids.mapped('amount_base'))
                if record.exchange_rate and record.exchange_rate != 0:
                    record.amount = total_base * record.exchange_rate
                else:
                    record.amount = total_base

    def action_post(self):
        for payment in self:
            if payment.state != 'draft':
                raise UserError("Only draft payments can be posted.")
            if payment.amount <= 0:
                raise UserError("Payment amount must be greater than zero.")
                
            if payment.is_multi_currency:
                if not payment.payment_line_ids:
                    raise UserError("Please add at least one payment line for multi-currency payment.")
                
                for line in payment.payment_line_ids:
                    account_currency = line.account_id.currency_id or payment.tenant_id.currency_id
                    if account_currency == line.currency_id:
                        account_amount = line.amount
                    elif account_currency == payment.tenant_id.currency_id:
                        account_amount = line.amount_base
                    else:
                        date = payment.date or fields.Date.context_today(payment)
                        rate = payment.tenant_id.currency_id._get_conversion_rate(
                            payment.tenant_id.currency_id, account_currency, payment.env.company, date
                        )
                        account_amount = line.amount_base * rate
                    
                    if payment.payment_type == 'receipt':
                        line.account_id.sudo().balance += account_amount
                    else:
                        line.account_id.sudo().balance -= account_amount
            else:
                if not payment.account_id:
                    raise UserError("Bank/Cash Account is required for single currency payment.")
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
                
            if payment.is_multi_currency:
                for line in payment.payment_line_ids:
                    account_currency = line.account_id.currency_id or payment.tenant_id.currency_id
                    if account_currency == line.currency_id:
                        account_amount = line.amount
                    elif account_currency == payment.tenant_id.currency_id:
                        account_amount = line.amount_base
                    else:
                        date = payment.date or fields.Date.context_today(payment)
                        rate = payment.tenant_id.currency_id._get_conversion_rate(
                            payment.tenant_id.currency_id, account_currency, payment.env.company, date
                        )
                        account_amount = line.amount_base * rate
                    
                    if payment.payment_type == 'receipt':
                        line.account_id.sudo().balance -= account_amount
                    else:
                        line.account_id.sudo().balance += account_amount
            else:
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

class PaymentLine(models.Model):
    _name = 'havanoposdesk.payment.line'
    _description = 'Payment Line'

    payment_id = fields.Many2one('havanoposdesk.payment', string='Payment Reference', ondelete='cascade', required=True)
    tenant_id = fields.Many2one(related='payment_id.tenant_id', store=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Bank/Cash Account', required=True, domain="[('type', 'in', ['Bank', 'Cash']), ('active', '=', True)]")
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        required=True,
        domain="[('tenant_id', '=', tenant_id)]",
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else False
    )
    exchange_rate = fields.Float(string='Exchange Rate', default=1.0, digits=(12, 6))
    amount = fields.Float(string='Amount', required=True, default=0.0)
    amount_base = fields.Float(string='Base Amount', compute='_compute_amount_base', store=True)

    @api.constrains('payment_id', 'currency_id')
    def _check_currency_belongs_to_tenant(self):
        for line in self:
            tenant = line.payment_id.tenant_id
            self.env['res.currency']._validate_tenant_currency(line.currency_id, tenant)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            payment = self.env['havanoposdesk.payment'].browse(vals.get('payment_id'))
            if payment.tenant_id and not vals.get('currency_id'):
                vals['currency_id'] = payment.tenant_id.currency_id.id
            if vals.get('currency_id'):
                self.env['res.currency']._validate_tenant_currency(vals['currency_id'], payment.tenant_id)
        return super().create(vals_list)

    def write(self, vals):
        for line in self:
            payment = self.env['havanoposdesk.payment'].browse(vals.get('payment_id', line.payment_id.id))
            if 'currency_id' in vals:
                self.env['res.currency']._validate_tenant_currency(vals['currency_id'], payment.tenant_id)
            elif 'payment_id' in vals:
                self.env['res.currency']._validate_tenant_currency(line.currency_id, payment.tenant_id)
        return super().write(vals)

    @api.onchange('currency_id', 'payment_id')
    def _onchange_currency_id(self):
        if self.currency_id and self.tenant_id and self.tenant_id.currency_id:
            if self.currency_id == self.tenant_id.currency_id:
                self.exchange_rate = 1.0
            else:
                date = self.payment_id.date or fields.Date.context_today(self)
                rate = self.currency_id._get_conversion_rate(self.tenant_id.currency_id, self.currency_id, self.env.company, date)
                self.exchange_rate = rate or 1.0

    @api.onchange('account_id')
    def _onchange_line_account_id(self):
        """Auto-populate currency from the selected account on a payment line.

        When a bank/cash account is chosen and it carries a currency, that
        currency is copied to the payment line and the exchange rate is
        looked up automatically.
        """
        if self.account_id and self.account_id.currency_id:
            self.currency_id = self.account_id.currency_id
            self._onchange_currency_id()

    @api.depends('amount', 'exchange_rate')
    def _compute_amount_base(self):
        for record in self:
            if record.exchange_rate and record.exchange_rate != 0:
                record.amount_base = record.amount / record.exchange_rate
            else:
                record.amount_base = record.amount
