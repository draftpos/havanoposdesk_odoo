import logging
from odoo import models, fields, api, _
from datetime import datetime, time
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class Sale(models.Model):
    _name = 'havanoposdesk.sale'
    _description = 'Sale'
    _order = 'date desc, id desc'

    _sql_constraints = [
        ('local_invoice_id_tenant_uniq', 'unique(local_invoice_id, tenant_id)', 'The Local Invoice ID must be unique per tenant!')
    ]

    def _default_posting_time(self):
        now_utc = fields.Datetime.now()
        now_local = fields.Datetime.context_timestamp(self, now_utc)
        return now_local.hour + now_local.minute / 60.0

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    customer = fields.Many2one('havanoposdesk.customer', string='Customer', required=True)
    customer_balance = fields.Float(related='customer.balance', string='Customer Balance')

    
    store = fields.Char(string='Store Name')
    posting_date = fields.Date(string='Posting Date', default=fields.Date.context_today)
    posting_time = fields.Float(string='Posting Time', default=_default_posting_time)
    local_invoice_id = fields.Char(string='Local Invoice ID', copy=False)
    
    is_return = fields.Boolean(string='Is Credit Note', default=False)
    is_quotation = fields.Boolean(string='Is Quotation', default=False)
    return_id = fields.Many2one('havanoposdesk.sale', string='Original Sale')
    return_sale_ids = fields.One2many('havanoposdesk.sale', 'return_id', string='Credit Notes')
    invoice_type = fields.Char(string='Type', compute='_compute_invoice_type', store=True)

    @api.constrains('local_invoice_id', 'tenant_id')
    def _check_local_invoice_id_uniqueness(self):
        for sale in self:
            if sale.local_invoice_id:
                duplicate = self.search([
                    ('tenant_id', '=', sale.tenant_id.id),
                    ('local_invoice_id', '=', sale.local_invoice_id),
                    ('id', '!=', sale.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(_("The Local Invoice ID must be unique per tenant!"))

    @api.depends('is_return', 'is_quotation')
    def _compute_invoice_type(self):
        for record in self:
            if record.is_return:
                record.invoice_type = 'Credit Note'
            elif record.is_quotation:
                record.invoice_type = 'Quotation'
            else:
                record.invoice_type = 'Sales Invoice'
    
    def _default_account_id(self):
        return self.env['havanoposdesk.account'].search([
            ('type', 'in', ['Cash', 'Bank']),
            ('active', '=', True),
            ('is_on_account', '=', False),
        ], limit=1).id

    payment_status = fields.Selection([
        ('cash', 'Paid'),
        ('partial', 'Partial'),
        ('account', 'On Account')
    ], string='Payment Status', default='cash', required=True)
    payment_status_display = fields.Selection([
        ('cash', 'Paid'),
        ('account', 'On Account')
    ], string='Payment Status', compute='_compute_payment_status_display', inverse='_inverse_payment_status_display', store=True)
    payment_policy = fields.Selection([
        ('single', 'Single Payment'),
        ('multi', 'Split / Multi-Currency Payment')
    ], string='Payment Policy', default='single')
    account_id = fields.Many2one('havanoposdesk.account', string='Deposit Account', domain="[('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]", default=_default_account_id)
    pos_payment_id = fields.Many2one('havanoposdesk.payment', string='POS Payment Batch')
    payment_ids = fields.One2many('havanoposdesk.payment', 'sale_id', string='Payments')
    
    line_ids = fields.One2many('havanoposdesk.sale.line', 'sale_id', string='Items')

    def _default_store_id(self):
        return self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1).id

    # View-required fields to avoid undefined errors
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
        default=_default_store_id
    )
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    exchange_rate = fields.Float(string='Exchange Rate', default=1.0, digits=(12, 6))

    allow_multi_currency = fields.Boolean(related='tenant_id.allow_multi_currency')



    @api.onchange('customer')
    def _onchange_customer(self):
        if self.customer:
            target_currency = self.customer.currency_id
            self.currency_id = target_currency.id
            
            # Auto-fetch exchange rate for the target currency
            if target_currency and self.tenant_id and self.tenant_id.currency_id:
                if target_currency == self.tenant_id.currency_id:
                    self.exchange_rate = 1.0
                else:
                    date = self.date or fields.Date.context_today(self)
                    rate = target_currency._get_conversion_rate(
                        self.tenant_id.currency_id, target_currency, self.env.company, date
                    )
                    self.exchange_rate = rate or 1.0

    @api.onchange('currency_id', 'tenant_id')
    def _onchange_currency_id(self):
        if self.currency_id and self.tenant_id and self.tenant_id.currency_id:
            if self.currency_id == self.tenant_id.currency_id:
                self.exchange_rate = 1.0
            else:
                # Odoo's res.currency stores rate as: 1 base = X foreign
                date = self.date or fields.Date.context_today(self)
                rate = self.currency_id._get_conversion_rate(self.tenant_id.currency_id, self.currency_id, self.env.company, date)
                self.exchange_rate = rate or 1.0
            if self.line_ids:
                self.line_ids._recompute_prices_for_currency()
    terminal_id = fields.Many2one(
        'havanoposdesk.pos.terminal', 
        string='POS Terminal', 
        default=lambda self: self.env.user.selected_terminal_id.id if self.env.user.selected_terminal_id else False
    )
    pricelist_id = fields.Many2one(
        'havanoposdesk.pricelist',
        string='Pricelist'
    )
    allowed_pricelist_ids = fields.Many2many(
        'havanoposdesk.pricelist',
        compute='_compute_allowed_pricelist_ids',
        string='Allowed Pricelists'
    )

    @api.depends('store_id', 'store_id.pricelist_ids')
    def _compute_allowed_pricelist_ids(self):
        for sale in self:
            if sale.store_id:
                sale.allowed_pricelist_ids = sale.store_id.pricelist_ids
            else:
                sale.allowed_pricelist_ids = self.env['havanoposdesk.pricelist'].browse()

    @api.onchange('store_id')
    def _onchange_store_id_pricelist(self):
        if self.store_id:
            if self.store_id.pricelist_id:
                self.pricelist_id = self.store_id.pricelist_id.id
            else:
                self.pricelist_id = False
        else:
            self.pricelist_id = False

    @api.onchange('pricelist_id')
    def _onchange_pricelist_id(self):
        # Auto-set the document currency from the pricelist currency
        if self.pricelist_id and self.pricelist_id.currency_id:
            self.currency_id = self.pricelist_id.currency_id.id
            # Trigger exchange rate fetch
            self._onchange_currency_id()
        elif self.pricelist_id and not self.pricelist_id.currency_id:
            # No currency on pricelist means base currency
            if self.tenant_id and self.tenant_id.currency_id:
                self.currency_id = self.tenant_id.currency_id.id
                self.exchange_rate = 1.0
        if self.line_ids:
            for line in self.line_ids:
                line._onchange_product_uom()

    date = fields.Datetime(string='Sale Date', default=fields.Datetime.now, required=True)
    amount_untaxed = fields.Float(string='Untaxed Amount', compute='_compute_amount_total', store=True)
    amount_tax = fields.Float(string='Taxes', compute='_compute_amount_total', store=True)
    amount_total = fields.Float(string='Total Amount', compute='_compute_amount_total', store=True)

    # Foreign-currency footer totals (document currency, not base)
    amount_untaxed_fc = fields.Float(string='Total Excl (FC)', compute='_compute_fc_totals', store=True)
    amount_tax_fc = fields.Float(string='Total Tax (FC)', compute='_compute_fc_totals', store=True)
    amount_total_fc = fields.Float(string='Total Incl (FC)', compute='_compute_fc_totals', store=True)
    is_cross_currency = fields.Boolean(
        string='Cross-Currency', compute='_compute_is_cross_currency', store=True
    )

    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    amount_total_base = fields.Float(string='Base Total', compute='_compute_amount_total_base', store=True)
    amount_paid_base = fields.Float(string='Paid (Base)', compute='_compute_amount_paid_base', store=True)
    amount_balance_base = fields.Float(string='Balance Due (Base)', compute='_compute_amount_paid_base', store=True)
    amount_paid = fields.Float(string='Paid Amount', compute='_compute_amount_paid_base', store=True)
    amount_balance = fields.Float(string='Balance Due', compute='_compute_amount_paid_base', store=True)
    single_payment_amount = fields.Float(string='Payment Amount', compute='_compute_single_payment_amount', store=True, readonly=False)
    
    total_cost = fields.Float(string='Total Cost', compute='_compute_total_cost', store=True)
    salesperson_id = fields.Many2one('res.users', string='Salesperson', default=lambda self: self.env.user.id)
    is_tax_enabled = fields.Boolean(related='tenant_id.enable_tax', string='Tax Enabled')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True)

    # ZIMRA Fiscalization Response Fields
    fiscal_status = fields.Selection([
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('fiscalized', 'Fiscalized'),
        ('PENDING_SYNC', 'Pending Sync (Offline)'),
        ('failed', 'Failed')
    ], string='Fiscal Status', default='not_required')
    fiscal_qr_code = fields.Text(string='ZIMRA QR Code Link')
    fiscal_verification_code = fields.Char(string='Verification Code')
    fiscal_receipt_counter = fields.Integer(string='Receipt Counter')
    fiscal_global_no = fields.Char(string='ZIMRA Global Invoice No')
    fiscal_device_id = fields.Char(string='Device ID')
    fiscal_device_serial = fields.Char(string='EFD Device Serial')
    fiscal_day = fields.Char(string='Fiscal Day')
    fiscal_error = fields.Text(string='Fiscalization Error')

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'line_ids.amount')
    def _compute_amount_total(self):
        for record in self:
            record.amount_untaxed = sum(record.line_ids.mapped('price_subtotal'))
            record.amount_tax = sum(record.line_ids.mapped('price_tax'))
            record.amount_total = sum(record.line_ids.mapped('amount'))

    @api.depends('amount_total', 'exchange_rate')
    def _compute_amount_total_base(self):
        for record in self:
            if record.exchange_rate and record.exchange_rate != 0:
                record.amount_total_base = record.amount_total / record.exchange_rate
            else:
                record.amount_total_base = record.amount_total

    @api.depends('currency_id', 'tenant_currency_id')
    def _compute_is_cross_currency(self):
        for record in self:
            record.is_cross_currency = (
                bool(record.currency_id)
                and bool(record.tenant_currency_id)
                and record.currency_id != record.tenant_currency_id
            )

    @api.depends('amount_untaxed', 'amount_tax', 'amount_total', 'exchange_rate', 'currency_id', 'tenant_currency_id')
    def _compute_fc_totals(self):
        """Compute footer totals expressed in the document's foreign currency.

        If the document currency is the base currency (company currency), the
        foreign currency equivalent is calculated by multiplying base totals by the exchange rate.
        Otherwise, the document is already in foreign currency, so we store the document totals.
        """
        for record in self:
            if record.currency_id == record.tenant_currency_id:
                rate = record.exchange_rate if record.exchange_rate else 1.0
                record.amount_untaxed_fc = record.amount_untaxed * rate
                record.amount_tax_fc = record.amount_tax * rate
                record.amount_total_fc = record.amount_total * rate
            else:
                rate = record.exchange_rate if record.exchange_rate else 1.0
                record.amount_untaxed_fc = record.amount_untaxed / rate
                record.amount_tax_fc = record.amount_tax / rate
                record.amount_total_fc = record.amount_total / rate

    @api.onchange('account_id')
    def _onchange_account_id(self):
        if self.account_id and self.account_id.is_silent_on_account():
            self.payment_status = 'account'
            self.payment_status_display = 'account'

    @api.depends('payment_status')
    def _compute_payment_status_display(self):
        for record in self:
            record.payment_status_display = 'cash' if record.payment_status == 'cash' else 'account'

    def _inverse_payment_status_display(self):
        for record in self:
            if record.payment_status == 'partial' and record.payment_status_display == 'account':
                continue
            record.payment_status = record.payment_status_display or 'cash'

    @api.depends(
        'payment_ids.amount', 'payment_ids.amount_base', 'payment_ids.state',
        'payment_ids.payment_type', 'payment_ids.currency_id', 'amount_total',
        'amount_total_base', 'payment_status', 'currency_id', 'exchange_rate'
    )
    def _compute_amount_paid_base(self):
        for record in self:
            posted = record.payment_ids.filtered(
                lambda p: p.state == 'posted' and p.payment_type == 'receipt'
            )
            record.amount_paid_base = sum(posted.mapped('amount_base'))
            paid_doc = 0.0
            for payment in posted:
                if payment.currency_id == record.currency_id:
                    paid_doc += payment.amount
                else:
                    rate = record.exchange_rate if record.exchange_rate else 1.0
                    paid_doc += payment.amount_base * rate
            record.amount_paid = paid_doc
            if record.payment_status == 'cash':
                record.amount_balance_base = 0.0
                record.amount_balance = 0.0
            else:
                record.amount_balance_base = max(record.amount_total_base - record.amount_paid_base, 0.0)
                record.amount_balance = max(record.amount_total - paid_doc, 0.0)

    @api.depends('amount_total')
    def _compute_single_payment_amount(self):
        for record in self:
            if record.single_payment_amount:
                continue
            record.single_payment_amount = record.amount_total

    @api.depends('line_ids.cost_price', 'line_ids.accepted_qty', 'is_return')
    def _compute_total_cost(self):
        for record in self:
            sign = -1.0 if record.is_return else 1.0
            record.total_cost = sum(line.cost_price * line.accepted_qty for line in record.line_ids) * sign

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))

            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    if vals.get('is_quotation'):
                        vals['name'] = tenant._get_next_sequence('quotation')
                    elif vals.get('is_return'):
                        vals['name'] = tenant._get_next_sequence('sale_ret')
                    else:
                        vals['name'] = tenant._get_next_sequence('sale')
                else:
                    if vals.get('is_quotation'):
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.quotation') or 'New'
                    elif vals.get('is_return'):
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale.return') or 'New'
                    else:
                        vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.sale') or 'New'
            
            # Default account_id for cash sales if not provided
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if vals.get('payment_status', 'cash') == 'cash' and not vals.get('account_id'):
                domain = [('type', 'in', ['Cash', 'Bank']), ('is_on_account', '=', False)]
                if tenant_id:
                    domain.append(('tenant_id', '=', tenant_id))
                account = self.env['havanoposdesk.account'].search(domain, limit=1)
                if account:
                    vals['account_id'] = account.id
            
            # Sync store and store_id
            if 'store' in vals and not vals.get('store_id'):
                domain = [('name', '=', vals['store'])]
                if tenant_id:
                    domain.append(('tenant_id', '=', tenant_id))
                store = self.env['havanoposdesk.store'].search(domain, limit=1)
                if store:
                    vals['store_id'] = store.id
            elif 'store_id' in vals and not vals.get('store'):
                store = self.env['havanoposdesk.store'].browse(vals['store_id'])
                if store:
                    vals['store'] = store.name
                    
            # Sync date and posting_date / posting_time
            if 'date' in vals and not vals.get('posting_date'):
                dt = fields.Datetime.to_datetime(vals['date'])
                vals['posting_date'] = dt.date()
                vals['posting_time'] = dt.hour + dt.minute / 60.0
            elif 'posting_date' in vals and not vals.get('date'):
                p_date = fields.Date.to_date(vals['posting_date'])
                p_time = vals.get('posting_time', 0.0)
                hours = int(p_time)
                minutes = int((p_time - hours) * 60)
                vals['date'] = datetime.combine(p_date, time(hours, minutes))

            # Ensure currency_id is set for API/mobile sync where onchange isn't triggered
            if not vals.get('currency_id'):
                if vals.get('customer'):
                    customer = self.env['havanoposdesk.customer'].browse(vals['customer'])
                    if customer.currency_id:
                        vals['currency_id'] = customer.currency_id.id
                if not vals.get('currency_id'):
                    tenant_id_val = vals.get('tenant_id') or self.env.user.tenant_id.id
                    if tenant_id_val:
                        tenant = self.env['havanoposdesk.tenant'].browse(tenant_id_val)
                        if tenant.currency_id:
                            vals['currency_id'] = tenant.currency_id.id
                    if not vals.get('currency_id'):
                        vals['currency_id'] = self.env.company.currency_id.id

        sales = super().create(vals_list)
        
        for sale in sales:
            # Mobile app syncs often include pos_payment_id. If present, or explicitly confirmed, auto-post.
            if sale.state in ['confirmed', 'done'] or sale.pos_payment_id or self.env.context.get('auto_post_sale'):
                # Set to draft temporarily to let action_post execute
                sale.state = 'draft'
                sale.action_post()
        return sales

    def write(self, vals):
        from odoo.exceptions import ValidationError
        allowed_post_fields = [
            'state', 'fiscal_status', 'fiscal_qr_code', 'fiscal_verification_code',
            'fiscal_receipt_counter', 'fiscal_global_no', 'fiscal_device_id',
            'fiscal_device_serial', 'fiscal_day', 'fiscal_error'
        ]
        for record in self:
            if record.state != 'draft' and any(f not in allowed_post_fields for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed sale. Please cancel it first.")

        # Sync values on write
        if 'store' in vals and 'store_id' not in vals:
            for record in self:
                domain = [('name', '=', vals['store'])]
                if record.tenant_id:
                    domain.append(('tenant_id', '=', record.tenant_id.id))
                store = self.env['havanoposdesk.store'].search(domain, limit=1)
                if store:
                    vals['store_id'] = store.id
                break # Only checking first record's tenant is usually sufficient for batch writes of the same store
        elif 'store_id' in vals and 'store' not in vals:
            store = self.env['havanoposdesk.store'].browse(vals['store_id'])
            if store:
                vals['store'] = store.name

        if 'date' in vals and 'posting_date' not in vals:
            dt = fields.Datetime.to_datetime(vals['date'])
            vals['posting_date'] = dt.date()
            vals['posting_time'] = dt.hour + dt.minute / 60.0
        elif 'posting_date' in vals and 'date' not in vals:
            p_date = fields.Date.to_date(vals['posting_date'])
            p_time = vals.get('posting_time') or (self.posting_time if hasattr(self, 'posting_time') else 0.0)
            hours = int(p_time)
            minutes = int((p_time - hours) * 60)
            vals['date'] = datetime.combine(p_date, time(hours, minutes))

        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state != 'draft':
                raise ValidationError("You cannot delete a confirmed sale. Please cancel it first.")
        return super().unlink()

    def action_print(self):
        """ Open HTML preview in browser — user can print from there. """
        self.ensure_one()
        return self.env.ref('havanoposdesk_odoo.action_report_sale_document_html').report_action(self)

    def action_post_and_print(self):
        self.ensure_one()
        self.action_post()
        return self.action_print()

    def _is_on_account_account(self, account, payment_method_name=None):
        Account = self.env['havanoposdesk.account']
        return Account.is_on_account_method(account, payment_method_name)

    def _payment_amount_base(self, amount, exchange_rate):
        rate = exchange_rate if exchange_rate and exchange_rate != 0 else 1.0
        return amount / rate

    def _post_sale_payments(self):
        """Post real receipts only. Cap at the invoice total. Skip on-account modes."""
        self.ensure_one()
        sale = self
        remaining_base = sale.amount_total_base
        used_on_account = sale._is_on_account_account(sale.account_id)

        def _cap_and_post(payment):
            nonlocal remaining_base
            if remaining_base <= 0.0001:
                if payment.state == 'draft':
                    payment.unlink()
                return 0.0
            if payment.amount_base > remaining_base + 0.0001:
                rate = payment.exchange_rate if payment.exchange_rate and payment.exchange_rate != 0 else 1.0
                payment.amount = remaining_base * rate
            if payment.amount <= 0:
                if payment.state == 'draft':
                    payment.unlink()
                return 0.0
            if payment.state == 'draft':
                payment.action_post()
            remaining_base = max(remaining_base - payment.amount_base, 0.0)
            return payment.amount_base

        existing = sale.payment_ids.filtered(lambda p: p.state != 'cancelled')
        silent = existing.filtered(lambda p: sale._is_on_account_account(p.account_id))
        if silent:
            used_on_account = True
            silent.filtered(lambda p: p.state == 'draft').unlink()

        real = sale.payment_ids.filtered(
            lambda p: p.state != 'cancelled' and not sale._is_on_account_account(p.account_id)
        )

        if real:
            for payment in real:
                _cap_and_post(payment)
        elif sale.payment_policy == 'multi' and not used_on_account:
            raise ValidationError("You must add at least one payment entry for cash sales in the Payment Breakdown tab.")
        elif not used_on_account:
            if not sale.account_id:
                raise ValidationError("You must select a Deposit Account for Single Payment cash sales.")
            payment_amount = sale.single_payment_amount if sale.single_payment_amount > 0 else sale.amount_total
            requested_base = sale._payment_amount_base(payment_amount, sale.exchange_rate)
            if requested_base > remaining_base + 0.0001:
                payment_amount = remaining_base * (sale.exchange_rate if sale.exchange_rate and sale.exchange_rate != 0 else 1.0)
            elif requested_base + 0.0001 >= remaining_base:
                payment_amount = sale.amount_total
            if payment_amount > 0:
                payment = self.env['havanoposdesk.payment'].create([{
                    'payment_type': 'receipt',
                    'partner_type': 'customer',
                    'customer_id': sale.customer.id,
                    'account_id': sale.account_id.id,
                    'currency_id': sale.currency_id.id,
                    'exchange_rate': sale.exchange_rate,
                    'amount': payment_amount,
                    'date': sale.posting_date or fields.Date.context_today(sale),
                    'tenant_id': sale.tenant_id.id,
                    'sale_id': sale.id,
                }])
                _cap_and_post(payment)

        paid_base = sum(
            sale.payment_ids.filtered(lambda p: p.state == 'posted' and p.payment_type == 'receipt').mapped('amount_base')
        )
        if used_on_account:
            new_status = 'partial'
        elif paid_base + 0.0001 >= sale.amount_total_base:
            new_status = 'cash'
        elif paid_base > 0:
            new_status = 'partial'
        else:
            new_status = 'account'
        sale.write({'payment_status': new_status})

    def action_post(self):
        for sale in self:
            if sale.state != 'draft':
                continue
                
            if sale.is_quotation:
                sale.write({'state': 'done'})
                continue
            
            # Handle payments
            if sale.payment_status != 'account':
                sale._post_sale_payments()

            for line in sale.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                if base_qty > 0:
                    # Update price on parent product
                    if not sale.is_return:
                        base_rate = line.rate
                        base_cost = line.cost_price
                        line.product_id.sudo().write({
                            'selling_price': base_rate,
                            'buying_price': (base_cost / line.uom_qty_multiplier) if line.uom_qty_multiplier else base_cost,
                        })

                    # Determine products for inventory changes
                    if line.product_id.is_bundle:
                        products_to_process = [(comp.product_id, base_qty * comp.qty) for comp in line.product_id.bundle_item_ids]
                    else:
                        products_to_process = [(line.product_id, base_qty)]

                    for product_id, item_base_qty in products_to_process:
                        if not product_id.track_qty:
                            continue
                        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                            ('product_id', '=', product_id.id),
                            ('store', '=', sale.store)
                        ], limit=1)
                        
                        current_qty = valuation.on_hand_qty if valuation else 0.0
                        if sale.is_return:
                            new_balance = current_qty + item_base_qty
                        else:
                            new_balance = current_qty - item_base_qty

                        if valuation:
                            valuation.write({'on_hand_qty': new_balance})
                        else:
                            self.env['havanoposdesk.stock.valuation'].sudo().create({
                                'product_id': product_id.id,
                                'store': sale.store,
                                'on_hand_qty': new_balance,
                                'tenant_id': product_id.tenant_id.id,
                            })

                        if sale.is_return:
                            # Add back to stock
                            self.env['havanoposdesk.stock.ledger'].sudo().create({
                                'product_id': product_id.id,
                                'in_qty': item_base_qty,
                                'out_qty': 0.0,
                                'balance_qty': new_balance,
                                'buying_price': line.cost_price / line.uom_qty_multiplier if line.uom_qty_multiplier else line.cost_price,
                                'store': sale.store,
                                'type': 'Credit Note',
                                'doc_no': sale.name,
                                'tenant_id': product_id.tenant_id.id,
                            })
                        else:
                            # Create Ledger Entry using sudo()
                            self.env['havanoposdesk.stock.ledger'].sudo().create({
                                'product_id': product_id.id,
                                'in_qty': 0.0,
                                'out_qty': item_base_qty,
                                'balance_qty': new_balance,
                                'buying_price': line.cost_price / line.uom_qty_multiplier if line.uom_qty_multiplier else line.cost_price,
                                'store': sale.store,
                                'type': 'Sale',
                                'doc_no': sale.name,
                                'tenant_id': product_id.tenant_id.id,
                            })
                elif base_qty < 0:
                    if line.product_id.is_bundle:
                        products_to_process = [(comp.product_id, base_qty * comp.qty) for comp in line.product_id.bundle_item_ids]
                    else:
                        products_to_process = [(line.product_id, base_qty)]

                    for product_id, item_base_qty in products_to_process:
                        if not product_id.track_qty:
                            continue
                        valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                            ('product_id', '=', product_id.id),
                            ('store', '=', sale.store)
                        ], limit=1)
                        
                        current_qty = valuation.on_hand_qty if valuation else 0.0
                        if sale.is_return:
                            new_balance = current_qty + item_base_qty
                        else:
                            new_balance = current_qty - item_base_qty

                        if valuation:
                            valuation.write({'on_hand_qty': new_balance})
                        else:
                            self.env['havanoposdesk.stock.valuation'].sudo().create({
                                'product_id': product_id.id,
                                'store': sale.store,
                                'on_hand_qty': new_balance,
                                'tenant_id': product_id.tenant_id.id,
                            })

                        # Return sale: add back to stock
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': product_id.id,
                            'in_qty': abs(item_base_qty),
                            'out_qty': 0.0,
                            'balance_qty': new_balance,
                            'store': sale.store,
                            'type': 'Return',
                            'doc_no': sale.name,
                            'tenant_id': product_id.tenant_id.id,
                        })
            sale.write({'state': 'done'})
            sale._trigger_fiscalization()

    def _trigger_fiscalization(self):
        for sale in self:
            if sale.is_quotation:
                continue
            store = sale.store_id
            tenant = sale.tenant_id
            is_enabled = (store and store.enable_fiscalization) or (tenant and tenant.enable_fiscalization)
            if not is_enabled:
                sale.write({'fiscal_status': 'not_required'})
                continue
            try:
                from ...core.models.fiscal_service import get_zimra_service
                service = get_zimra_service(self.env)
                res = service.process_sale_fiscalization(sale)
                if res.get('status') in ('fiscalized', 'PENDING_SYNC'):
                    sale.write({
                        'fiscal_status': res.get('status'),
                        'fiscal_qr_code': res.get('qr_code', ''),
                        'fiscal_verification_code': res.get('verification_code', ''),
                        'fiscal_receipt_counter': res.get('receipt_counter', 0),
                        'fiscal_global_no': res.get('global_no', ''),
                        'fiscal_device_id': res.get('device_id', ''),
                        'fiscal_device_serial': res.get('device_serial', ''),
                        'fiscal_day': res.get('fiscal_day', ''),
                        'fiscal_error': False,
                    })
                else:
                    sale.write({
                        'fiscal_status': 'failed',
                        'fiscal_error': str(res.get('error', 'Fiscalization failed')),
                    })
            except Exception as e:
                sale.write({
                    'fiscal_status': 'failed',
                    'fiscal_error': f"Fiscalization trigger exception: {e}",
                })

    def action_retry_fiscalization(self):
        for sale in self:
            sale._trigger_fiscalization()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fiscalization Retried',
                'message': 'Fiscalization process has been re-triggered.',
                'type': 'info',
                'sticky': False,
            }
        }

    @api.model
    def cron_retry_pending_fiscalization(self):
        pending_sales = self.sudo().search([
            ('state', '=', 'done'),
            ('fiscal_status', 'in', ['PENDING_SYNC', 'failed'])
        ], limit=50)
        _logger.info("[ZIMRA CRON] Retrying fiscalization for %s pending sales", len(pending_sales))
        for sale in pending_sales:
            sale._trigger_fiscalization()


    def action_cancel(self):
        for sale in self:
            if sale.state not in ['confirmed', 'done']:
                continue
                
            if sale.is_quotation:
                sale.write({'state': 'cancelled'})
                continue
            
            for line in sale.line_ids:
                base_qty = line.accepted_qty * line.uom_qty_multiplier
                if line.product_id.is_bundle:
                    products_to_process = [(comp.product_id, base_qty * comp.qty) for comp in line.product_id.bundle_item_ids]
                else:
                    products_to_process = [(line.product_id, base_qty)]

                for product_id, item_base_qty in products_to_process:
                    if not product_id.track_qty:
                        continue
                    # Create reverse ledger entry using sudo()
                    orig_ledgers = self.env['havanoposdesk.stock.ledger'].sudo().search([
                        ('doc_no', '=', sale.name),
                        ('product_id', '=', product_id.id),
                        ('type', 'in', ['Sale', 'Return', 'Credit Note'])
                    ])
                    for orig_ledger in orig_ledgers:
                        self.env['havanoposdesk.stock.ledger'].sudo().create({
                            'product_id': product_id.id,
                            'in_qty': orig_ledger.out_qty,
                            'out_qty': orig_ledger.in_qty,
                            'balance_qty': product_id.opening_stock,
                            'buying_price': orig_ledger.buying_price,
                            'store': sale.store,
                            'type': 'Sale Cancelled',
                            'doc_no': sale.name,
                            'tenant_id': product_id.tenant_id.id,
                        })

                    # Update Valuation Entry using sudo()
                    valuation = self.env['havanoposdesk.stock.valuation'].sudo().search([
                        ('product_id', '=', product_id.id),
                        ('store', '=', sale.store)
                    ], limit=1)
                    if valuation:
                        if sale.is_return:
                            valuation.write({'on_hand_qty': valuation.on_hand_qty - item_base_qty})
                        else:
                            valuation.write({'on_hand_qty': valuation.on_hand_qty + item_base_qty})


            # Reverse POS Payment batch amounts and account balances
            if sale.payment_status == 'cash':
                for payment in sale.payment_ids:
                    if payment.state == 'posted':
                        payment.action_cancel()
                
            sale.write({'state': 'cancelled'})

    def action_draft(self):
        for sale in self:
            if sale.state != 'cancelled':
                continue
            sale.write({'state': 'draft'})

    @api.model
    def fields_get(self, allfields=None, attributes=None):
        res = super().fields_get(allfields=allfields, attributes=attributes)
        if 'store' in res:
            res['store']['searchable'] = False
            res['store']['sortable'] = False
        # Partial is API-only; keep Paid / On Account on the UI field.
        if 'payment_status' in res and res['payment_status'].get('selection'):
            res['payment_status']['selection'] = [
                option for option in res['payment_status']['selection'] if option[0] != 'partial'
            ]
        return res

class SaleLine(models.Model):
    _name = 'havanoposdesk.sale.line'
    _description = 'Sale Line'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    sale_id = fields.Many2one('havanoposdesk.sale', string='Sale', required=True, ondelete='cascade')
    store_id = fields.Many2one(related='sale_id.store_id', store=True)
    currency_id = fields.Many2one('res.currency', related='sale_id.currency_id', readonly=True)
    exchange_rate = fields.Float(related='sale_id.exchange_rate', readonly=True)
    product_id = fields.Many2one('havanoposdesk.product', string='Item', required=True)
    item_code = fields.Char(related='product_id.item_code', string='Product Code', readonly=True)
    accepted_qty = fields.Float(string='Accepted Quantity', default=1.0)
    rate = fields.Float(string='Rate')
    tax_ids = fields.Many2many('havanoposdesk.tax', string='Taxes', domain="[('tax_type', '=', 'Sales'), ('active', '=', True)]")
    price_subtotal = fields.Float(string='Subtotal', compute='_compute_amount', store=True)
    price_tax = fields.Float(string='Tax', compute='_compute_amount', store=True)
    amount = fields.Float(string='Total', compute='_compute_amount', store=True)

    # Foreign-currency equivalents — expressed in the document currency (FC)
    price_subtotal_fc = fields.Float(string='Rate (FC)', compute='_compute_fc_amounts', store=True)
    price_tax_fc = fields.Float(string='Tax (FC)', compute='_compute_fc_amounts', store=True)
    amount_fc = fields.Float(string='Total (FC)', compute='_compute_fc_amounts', store=True)

    uom_id = fields.Many2one('havanoposdesk.uom', string='UOM')
    uom_qty_multiplier = fields.Float(string='UOM Multiplier', default=1.0)
    available_uom_ids = fields.Many2many('havanoposdesk.uom', compute='_compute_available_uom_ids', store=False)
    cost_price = fields.Float(string='Cost Price', compute='_compute_cost_price', store=True, readonly=False)
    gross_profit = fields.Float(string='Gross Profit', compute='_compute_gross_profit', store=True)

    def _resolve_uom_multiplier(self, product_id, uom_id):
        """Return the qty_to_be_sold multiplier for a given product + UOM pair.
        Searches product.uom.price for the matching UOM, falling back to 1.0."""
        if not product_id or not uom_id:
            return 1.0
        price_rec = self.env['havanoposdesk.product.uom.price'].search([
            ('product_id', '=', product_id),
            ('uom_id', '=', uom_id),
        ], limit=1)
        if price_rec and price_rec.qty_to_be_sold:
            return price_rec.qty_to_be_sold
        return 1.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            product_id = vals.get('product_id')
            if product_id:
                product = self.env['havanoposdesk.product'].browse(product_id)
                if not vals.get('uom_id'):
                    if product.uom_id:
                        vals['uom_id'] = product.uom_id.id

                uom_id = vals.get('uom_id')
                provided = vals.get('uom_qty_multiplier')
                if not provided or provided == 1.0:
                    vals['uom_qty_multiplier'] = self._resolve_uom_multiplier(product_id, uom_id)

                if 'tax_ids' not in vals or not vals.get('tax_ids'):
                    if product.sale_tax_ids:
                        vals['tax_ids'] = [(6, 0, product.sale_tax_ids.ids)]
        return super().create(vals_list)

    def write(self, vals):
        # When uom_id changes on an existing line (e.g. user edits the web form),
        # re-resolve the multiplier unless the caller is explicitly setting it.
        if 'uom_id' in vals and 'uom_qty_multiplier' not in vals:
            uom_id = vals['uom_id']
            for line in self:
                product_id = vals.get('product_id', line.product_id.id)
                vals['uom_qty_multiplier'] = self._resolve_uom_multiplier(product_id, uom_id)
                break  # same UOM applied to all lines in the same write call
        return super().write(vals)

    @api.depends('price_subtotal', 'cost_price', 'accepted_qty', 'sale_id.is_return')
    def _compute_gross_profit(self):
        for line in self:
            sign = -1.0 if line.sale_id.is_return else 1.0
            total_cost = line.cost_price * line.accepted_qty * sign
            line.gross_profit = line.price_subtotal - total_cost

    @api.depends('product_id', 'rate')
    def _compute_cost_price(self):
        for line in self:
            if not line.product_id:
                line.cost_price = 0.0
                continue
            
            # If user manually changed the rate (selling price)
            if line.rate != line.product_id.selling_price:
                # Use Average cost from costing table
                avg_cost_rec = self.env['havanoposdesk.product.costing'].sudo().search([
                    ('product_id', '=', line.product_id.id),
                    ('cost_type', '=', 'average')
                ], order='id desc', limit=1)
                line.cost_price = avg_cost_rec.price if avg_cost_rec else (line.product_id.buying_price or line.product_id.cost_price or 0.0)
            else:
                # Use normal cost (product's buying_price or cost_price)
                line.cost_price = line.product_id.buying_price or line.product_id.cost_price or 0.0

    @api.depends('accepted_qty', 'rate', 'tax_ids', 'sale_id.is_return')
    def _compute_amount(self):
        for record in self:
            sign = -1.0 if record.sale_id.is_return else 1.0
            base_amount = record.accepted_qty * record.rate
            taxes = record.tax_ids

            inclusive_taxes = taxes.filtered(lambda t: t.is_inclusive)
            exclusive_taxes = taxes.filtered(lambda t: not t.is_inclusive)

            rate_incl = sum(inclusive_taxes.mapped('rate')) / 100.0
            rate_excl = sum(exclusive_taxes.mapped('rate')) / 100.0

            untaxed_amount = base_amount / (1.0 + rate_incl)
            inclusive_tax_amount = base_amount - untaxed_amount
            exclusive_tax_amount = untaxed_amount * rate_excl

            record.price_subtotal = untaxed_amount * sign
            record.price_tax = (inclusive_tax_amount + exclusive_tax_amount) * sign
            record.amount = record.price_subtotal + record.price_tax

    @api.depends('price_subtotal', 'price_tax', 'amount', 'exchange_rate', 'sale_id.exchange_rate', 'sale_id.currency_id', 'sale_id.tenant_currency_id')
    def _compute_fc_amounts(self):
        """Convert line amounts into the document's foreign currency.

        If the document currency is the base currency (company currency), the
        foreign currency equivalent is calculated by multiplying base amounts by the exchange rate.
        Otherwise, the document is already in foreign currency, so we store the document amounts.
        """
        for record in self:
            if record.sale_id.currency_id == record.sale_id.tenant_currency_id:
                rate = record.exchange_rate if record.exchange_rate else 1.0
                record.price_subtotal_fc = record.price_subtotal * rate
                record.price_tax_fc = record.price_tax * rate
                record.amount_fc = record.amount * rate
            else:
                rate = record.exchange_rate if record.exchange_rate else 1.0
                record.price_subtotal_fc = record.price_subtotal / rate
                record.price_tax_fc = record.price_tax / rate
                record.amount_fc = record.amount / rate

    @api.depends('product_id')
    def _compute_available_uom_ids(self):
        for line in self:
            if not line.product_id:
                line.available_uom_ids = False
                continue
            
            uom_ids = line.product_id.uom_id.ids if line.product_id.uom_id else []
            prices = self.env['havanoposdesk.product.uom.price'].search([
                ('product_id', '=', line.product_id.id),
                ('pricelist_id.type', '=', 'selling')
            ])
            uom_ids.extend(prices.mapped('uom_id.id'))
            line.available_uom_ids = [(6, 0, list(set(uom_ids)))]

    def _convert_price_to_document_currency(self, price, price_source_pricelist=None):
        """Convert a price from the pricelist/base currency to the document currency.
        
        If the pricelist has a currency set, that's the source currency.
        If not, prices are assumed to be in the tenant's base currency.
        
        If the source currency matches the document currency, no conversion needed.
        If they differ, multiply by the exchange rate (base → foreign) or divide (foreign → base).
        """
        sale = self.sale_id
        if not sale or not sale.currency_id or not sale.tenant_id or not sale.tenant_id.currency_id:
            return price
            
        doc_currency = sale.currency_id
        base_currency = sale.tenant_id.currency_id
        exchange_rate = sale.exchange_rate or 1.0
        
        # Determine the source currency of the price
        if price_source_pricelist and price_source_pricelist.currency_id:
            source_currency = price_source_pricelist.currency_id
        else:
            source_currency = base_currency  # default: prices are in base currency
        
        # No conversion needed if source matches document
        if source_currency == doc_currency:
            return price
        
        # Source is base currency, document is foreign → multiply by exchange rate
        if source_currency == base_currency:
            return price * exchange_rate
        
        # Source is foreign, document is base → divide by exchange rate
        if doc_currency == base_currency and exchange_rate:
            return price / exchange_rate
        
        # Both are different non-base currencies — rare edge case, return as-is
        return price

    @api.onchange('product_id', 'uom_id')
    def _onchange_product_uom(self):
        for line in self:
            if not line.product_id:
                line.uom_id = False
                line.uom_qty_multiplier = 1.0
                continue
                
            if not line.uom_id or line.uom_id.id not in line.available_uom_ids.ids:
                line.uom_id = line.product_id.uom_id
                
            line.tax_ids = [(6, 0, line.product_id.sale_tax_ids.ids)]
            
            price_record = False
            pricelist = line.sale_id.pricelist_id
            if pricelist:
                price_record = self.env['havanoposdesk.product.uom.price'].search([
                    ('product_id', '=', line.product_id.id),
                    ('uom_id', '=', line.uom_id.id),
                    ('pricelist_id', '=', pricelist.id)
                ], limit=1)
                
            if price_record:
                raw_price = price_record.price
                line.rate = line._convert_price_to_document_currency(raw_price, pricelist)
                line.uom_qty_multiplier = price_record.qty_to_be_sold
                base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                line.cost_price = base_cost * price_record.qty_to_be_sold
            else:
                if line.uom_id == line.product_id.uom_id:
                    base_price = line.product_id.selling_price
                    # Product selling_price is always in base currency
                    line.rate = line._convert_price_to_document_currency(base_price)
                    
                    base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                    line.cost_price = base_cost
                    line.uom_qty_multiplier = 1.0
                else:
                    fallback_record = self.env['havanoposdesk.product.uom.price'].search([
                        ('product_id', '=', line.product_id.id),
                        ('uom_id', '=', line.uom_id.id),
                        ('pricelist_id.type', '=', 'selling')
                    ], limit=1)
                    if fallback_record:
                        fallback_pricelist = fallback_record.pricelist_id
                        raw_price = fallback_record.price
                        line.rate = line._convert_price_to_document_currency(raw_price, fallback_pricelist)
                        line.uom_qty_multiplier = fallback_record.qty_to_be_sold
                        base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                        line.cost_price = base_cost * fallback_record.qty_to_be_sold
                    else:
                        base_price = line.product_id.selling_price
                        line.rate = line._convert_price_to_document_currency(base_price)
                        line.uom_qty_multiplier = 1.0

    def _recompute_prices_for_currency(self):
        for line in self:
            if not line.product_id:
                continue
            price_record = False
            pricelist = line.sale_id.pricelist_id
            if pricelist:
                price_record = self.env['havanoposdesk.product.uom.price'].search([
                    ('product_id', '=', line.product_id.id),
                    ('uom_id', '=', line.uom_id.id),
                    ('pricelist_id', '=', pricelist.id)
                ], limit=1)
                
            if price_record:
                raw_price = price_record.price
                line.rate = line._convert_price_to_document_currency(raw_price, pricelist)
                base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                line.cost_price = base_cost * price_record.qty_to_be_sold
            else:
                if line.uom_id == line.product_id.uom_id:
                    base_price = line.product_id.selling_price
                    line.rate = line._convert_price_to_document_currency(base_price)
                    base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                    line.cost_price = base_cost
                else:
                    fallback_record = self.env['havanoposdesk.product.uom.price'].search([
                        ('product_id', '=', line.product_id.id),
                        ('uom_id', '=', line.uom_id.id),
                        ('pricelist_id.type', '=', 'selling')
                    ], limit=1)
                    if fallback_record:
                        fallback_pricelist = fallback_record.pricelist_id
                        raw_price = fallback_record.price
                        line.rate = line._convert_price_to_document_currency(raw_price, fallback_pricelist)
                        base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                        line.cost_price = base_cost * fallback_record.qty_to_be_sold
                    else:
                        base_price = line.product_id.selling_price
                        line.rate = line._convert_price_to_document_currency(base_price)
                        base_cost = line.product_id.buying_price or line.product_id.cost_price or 0.0
                        line.cost_price = base_cost

    @api.onchange('rate')
    def _onchange_rate(self):
        if self.tenant_id.restrict_price_modification and not self.env.user.has_group('havanoposdesk_odoo.group_tenant_admin'):
            base_price = self.product_id.selling_price if self.product_id else 0.0
            self.rate = self._origin.rate if getattr(self, '_origin', False) else base_price
            return {
                'warning': {
                    'title': 'Price Modification Restricted',
                    'message': 'You cannot edit prices. Please contact the admin if you wish to change the price.'
                }
            }

        if self.product_id:
            expected_rate = self.product_id.selling_price
            if abs(self.rate - expected_rate) > 0.01:
                avg_cost_rec = self.env['havanoposdesk.product.costing'].sudo().search([
                    ('product_id', '=', self.product_id.id),
                    ('cost_type', '=', 'average')
                ], order='id desc', limit=1)
                base_cost = avg_cost_rec.price if avg_cost_rec else (self.product_id.buying_price or self.product_id.cost_price or 0.0)
                self.cost_price = base_cost
            else:
                base_cost = self.product_id.buying_price or self.product_id.cost_price or 0.0
                self.cost_price = base_cost

    @api.onchange('accepted_qty', 'product_id')
    def _onchange_qty(self):
        allow_negative = self.env.user.tenant_id.allow_negative_stock
        if not allow_negative and self.product_id and self.product_id.track_qty and self.accepted_qty > self.product_id.opening_stock:
            return {
                'warning': {
                    'title': 'Insufficient Stock',
                    'message': f'You only have {self.product_id.opening_stock} of {self.product_id.name} on hand.',
                }
            }

    @api.constrains('accepted_qty')
    def _check_stock(self):
        allow_negative = self.env.user.tenant_id.allow_negative_stock
        for line in self:
            if line.sale_id and line.sale_id.is_return:
                continue
            if line.accepted_qty < 0:
                continue
            if not allow_negative and line.product_id and line.product_id.track_qty and line.accepted_qty > line.product_id.opening_stock:
                raise ValidationError(f"You cannot sell {line.accepted_qty} of {line.product_id.name} because you only have {line.product_id.opening_stock} on hand.")
