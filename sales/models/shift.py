from odoo import models, fields, api

class Shift(models.Model):
    _name = 'havanoposdesk.shift'
    _description = 'Shift Operations'
    _order = 'start_date desc'

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default='New')
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', default=lambda self: self.env.user.tenant_id.id, index=True, readonly=True)
    user_id = fields.Many2one('res.users', string='Cashier', default=lambda self: self.env.user.id, required=True, domain="[('tenant_id', '=', tenant_id)]")
    store_id = fields.Many2one('havanoposdesk.store', string='Store', required=True, domain="[('tenant_id', '=', tenant_id)]")
    terminal_id = fields.Many2one('havanoposdesk.pos.terminal', string='Terminal', domain="[('store_id', '=', store_id)]")
    
    start_date = fields.Datetime(string='Opened At', default=fields.Datetime.now, required=True)
    end_date = fields.Datetime(string='Closed At')
    
    state = fields.Selection([
        ('open', 'Open'),
        ('closed', 'Closed')
    ], string='Status', default='open', required=True, tracking=True)

    currency_id = fields.Many2one('res.currency', string='Currency', related='tenant_id.currency_id', readonly=True)

    opening_cash = fields.Monetary(string='Opening Cash (Before)', currency_field='currency_id', default=0.0)
    actual_cash = fields.Monetary(string='Actual Cash (After)', currency_field='currency_id', default=0.0)
    expected_cash = fields.Monetary(string='Expected Cash', currency_field='currency_id', compute='_compute_expected_cash', store=True, compute_sudo=True)
    cash_difference = fields.Monetary(string='Difference', currency_field='currency_id', compute='_compute_cash_difference', store=True, compute_sudo=True)
    
    total_expenses = fields.Monetary(string='Total Expenses', currency_field='currency_id', compute='_compute_total_expenses', store=True, compute_sudo=True, readonly=False, default=0.0)
    total_credit_notes = fields.Monetary(string='Total Credit Notes', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)

    # Payment Breakdown
    amount_cash = fields.Monetary(string='Total Cash Payments', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)
    amount_card = fields.Monetary(string='Total Card Payments', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)
    amount_mobile = fields.Monetary(string='Total Mobile Payments', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)
    amount_bank = fields.Monetary(string='Total Bank Transfers', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)
    amount_other = fields.Monetary(string='Total Other Payments', currency_field='currency_id', compute='_compute_payments_breakdown', store=True, compute_sudo=True, readonly=False, default=0.0)

    sale_ids = fields.One2many('havanoposdesk.sale', 'shift_id', string='Sales')
    expense_ids = fields.One2many('havanoposdesk.expense', 'shift_id', string='Expenses')
    payment_ids = fields.One2many('havanoposdesk.payment', 'shift_id', string='Payments')
    cash_transfer_ids = fields.One2many('havanoposdesk.cash.transfer', 'shift_id', string='Cash Transfers / Cash Up')
    cash_transferred_amount = fields.Monetary(string='Total Cashed Up / Transferred', compute='_compute_cash_transferred', compute_sudo=True, currency_field='currency_id', store=True)
    cash_transfer_count = fields.Integer(string='Cash Transfers Count', compute='_compute_cash_transferred', compute_sudo=True)

    @staticmethod
    def _classify_account(account):
        if not account:
            return 'cash'
        name = (account.name or '').lower()
        if account.type == 'Cash':
            if any(m in name for m in ('mobile', 'ecocash', 'mpesa', 'airtel', 'omari', 'telecash', 'innbucks')):
                return 'mobile'
            return 'cash'
        elif account.type == 'Bank':
            if any(c in name for c in ('card', 'pos', 'visa', 'master', 'swipe')):
                return 'card'
            elif any(m in name for m in ('mobile', 'ecocash', 'mpesa', 'airtel', 'omari', 'telecash', 'innbucks')):
                return 'mobile'
            return 'bank'
        return 'other'

    @api.depends(
        'sale_ids.amount_total',
        'sale_ids.amount_total_base',
        'sale_ids.state',
        'sale_ids.is_return',
        'sale_ids.is_quotation',
        'sale_ids.payment_status',
        'sale_ids.account_id',
        'sale_ids.payment_ids.amount',
        'sale_ids.payment_ids.amount_base',
        'sale_ids.payment_ids.state',
        'sale_ids.payment_ids.account_id',
        'sale_ids.payment_ids.payment_line_ids.amount_base',
        'sale_ids.payment_ids.payment_line_ids.account_id',
        'payment_ids.amount',
        'payment_ids.amount_base',
        'payment_ids.state',
        'payment_ids.payment_type',
        'payment_ids.account_id',
        'payment_ids.transaction_category',
    )
    def _compute_payments_breakdown(self):
        for shift in self:
            cash = 0.0
            card = 0.0
            mobile = 0.0
            bank = 0.0
            other = 0.0
            credit_notes = 0.0

            # 1. Process Sales & Credit Notes
            valid_sales = shift.sale_ids.filtered(lambda s: s.state != 'cancelled' and not s.is_quotation)
            for sale in valid_sales:
                sale_amt = sale.amount_total_base or sale.amount_total
                if sale.is_return:
                    credit_notes += abs(sale_amt)
                    continue

                posted_payments = sale.payment_ids.filtered(lambda p: p.state != 'cancelled')
                if posted_payments:
                    for p in posted_payments:
                        if p.is_multi_currency and p.payment_line_ids:
                            for line in p.payment_line_ids:
                                cat = self._classify_account(line.account_id)
                                amt = line.amount_base or line.amount
                                if cat == 'cash': cash += amt
                                elif cat == 'card': card += amt
                                elif cat == 'mobile': mobile += amt
                                elif cat == 'bank': bank += amt
                                else: other += amt
                        else:
                            cat = self._classify_account(p.account_id)
                            amt = p.amount_base or p.amount
                            if cat == 'cash': cash += amt
                            elif cat == 'card': card += amt
                            elif cat == 'mobile': mobile += amt
                            elif cat == 'bank': bank += amt
                            else: other += amt
                elif sale.payment_status in ('cash', 'partial') and sale.account_id:
                    cat = self._classify_account(sale.account_id)
                    if cat == 'cash': cash += sale_amt
                    elif cat == 'card': card += sale_amt
                    elif cat == 'mobile': mobile += sale_amt
                    elif cat == 'bank': bank += sale_amt
                    else: other += sale_amt

            # 2. Process Standalone Customer Receipts / Payments (not linked to sales/expenses/transfers)
            standalone_payments = shift.payment_ids.filtered(
                lambda p: p.state == 'posted' and not p.sale_id and not p.expense_id and not p.transfer_id
            )
            for p in standalone_payments:
                cat = self._classify_account(p.account_id)
                amt = p.amount_base or p.amount
                if p.payment_type == 'receipt':
                    if cat == 'cash': cash += amt
                    elif cat == 'card': card += amt
                    elif cat == 'mobile': mobile += amt
                    elif cat == 'bank': bank += amt
                    else: other += amt
                elif p.payment_type == 'payment':
                    if cat == 'cash': cash -= amt
                    elif cat == 'card': card -= amt
                    elif cat == 'mobile': mobile -= amt
                    elif cat == 'bank': bank -= amt
                    else: other -= amt

            shift.amount_cash = cash
            shift.amount_card = card
            shift.amount_mobile = mobile
            shift.amount_bank = bank
            shift.amount_other = other
            shift.total_credit_notes = credit_notes

    @api.depends('expense_ids.amount', 'expense_ids.state', 'expense_ids.is_paid')
    def _compute_total_expenses(self):
        for shift in self:
            paid_posted_expenses = shift.expense_ids.filtered(lambda e: e.state == 'Posted' and e.is_paid)
            if paid_posted_expenses:
                shift.total_expenses = sum(paid_posted_expenses.mapped('amount'))
            elif not shift.total_expenses:
                shift.total_expenses = 0.0

    @api.depends('cash_transfer_ids.amount', 'cash_transfer_ids.state')
    def _compute_cash_transferred(self):
        for shift in self:
            posted_transfers = shift.cash_transfer_ids.filtered(lambda t: t.state == 'posted')
            shift.cash_transferred_amount = sum(posted_transfers.mapped('amount'))
            shift.cash_transfer_count = len(shift.cash_transfer_ids)

    @api.depends(
        'opening_cash',
        'amount_cash',
        'total_expenses',
        'total_credit_notes',
        'cash_transferred_amount',
        'sale_ids.amount_total',
        'sale_ids.state',
        'sale_ids.is_return',
        'expense_ids.amount',
        'expense_ids.state',
        'expense_ids.is_paid',
        'cash_transfer_ids.amount',
        'cash_transfer_ids.state',
        'payment_ids.amount',
        'payment_ids.state'
    )
    def _compute_expected_cash(self):
        for record in self:
            record.expected_cash = (record.opening_cash + record.amount_cash) - (record.total_credit_notes + record.total_expenses + record.cash_transferred_amount)

    @api.depends('actual_cash', 'expected_cash')
    def _compute_cash_difference(self):
        for record in self:
            record.cash_difference = record.actual_cash - record.expected_cash

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.shift') or 'New'
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
            if vals.get('store_id') and not vals.get('tenant_id'):
                store = self.env['havanoposdesk.store'].sudo().browse(vals['store_id'])
                if store and store.tenant_id:
                    vals['tenant_id'] = store.tenant_id.id
        return super(Shift, self).create(vals_list)

    def action_close_shift(self):
        for record in self:
            record.write({
                'state': 'closed',
                'end_date': fields.Datetime.now()
            })

    def action_cash_up(self):
        """Open Cash Transfer form pre-filled to transfer closing cash from branch to HQ/Main store."""
        self.ensure_one()
        # Find default store / HQ store for this tenant
        hq_store = self.env['havanoposdesk.store'].search([
            ('tenant_id', '=', self.tenant_id.id),
            ('is_default', '=', True),
        ], limit=1)
        if not hq_store or hq_store.id == self.store_id.id:
            hq_store = self.env['havanoposdesk.store'].search([
                ('tenant_id', '=', self.tenant_id.id),
                ('id', '!=', self.store_id.id),
            ], limit=1)

        amount_to_transfer = self.actual_cash if self.actual_cash > 0 else self.expected_cash
        if amount_to_transfer <= 0:
            amount_to_transfer = self.amount_cash

        # Auto-find source and target cash accounts
        from_acc = self.env['havanoposdesk.account'].search([
            ('tenant_id', '=', self.tenant_id.id),
            ('type', '=', 'Cash'),
            ('active', '=', True),
            '|', ('store_id', '=', self.store_id.id), ('store_ids', 'in', self.store_id.id)
        ], limit=1)
        
        to_acc = False
        if hq_store:
            to_acc = self.env['havanoposdesk.account'].search([
                ('tenant_id', '=', self.tenant_id.id),
                ('type', '=', 'Cash'),
                ('active', '=', True),
                '|', ('store_id', '=', hq_store.id), ('store_ids', 'in', hq_store.id)
            ], limit=1)

        return {
            'name': 'Shift Cash Up to HQ',
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.cash.transfer',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'target': 'current',
            'context': {
                'default_store_id': self.store_id.id,
                'default_from_branch_id': self.store_id.id,
                'default_to_branch_id': hq_store.id if hq_store else False,
                'default_from_account_id': from_acc.id if from_acc else False,
                'default_to_account_id': to_acc.id if to_acc else False,
                'default_amount': amount_to_transfer if amount_to_transfer > 0 else 0.0,
                'default_shift_id': self.id,
                'default_tenant_id': self.tenant_id.id,
                'default_reason': f"Shift Cash Up - {self.name} ({self.user_id.name})",
            },
        }

    def action_view_cash_transfers(self):
        self.ensure_one()
        return {
            'name': f"Cash Transfers - Shift {self.name}",
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.cash.transfer',
            'view_mode': 'list,form',
            'domain': [('shift_id', '=', self.id)],
            'context': {
                'default_shift_id': self.id,
                'default_store_id': self.store_id.id,
                'default_from_branch_id': self.store_id.id,
                'default_tenant_id': self.tenant_id.id,
            },
        }
