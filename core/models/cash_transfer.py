from odoo import fields, models, api, _
from odoo.exceptions import ValidationError, UserError

class CashTransfer(models.Model):
    _name = "havanoposdesk.cash.transfer"
    _inherit = ['havanoposdesk.audit.mixin']
    _description = "Cash Transfer between branches"
    _order = "date desc, id desc"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default="New",
    )
    tenant_id = fields.Many2one(
        "havanoposdesk.tenant",
        string="Tenant",
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1).id),
        index=True,
        readonly=True,
    )
    store_id = fields.Many2one(
        "havanoposdesk.store",
        string="Store",
        required=True,
        default=lambda self: self.env.user.default_store_id.id or (self.env.user.store_ids[0].id if self.env.user.store_ids else False),
        help="Store initiating the transfer.",
    )
    from_branch_id = fields.Many2one(
        "havanoposdesk.store",
        string="From Branch",
        required=True,
        default=lambda self: self.env.user.default_store_id.id or (self.env.user.store_ids[0].id if self.env.user.store_ids else False),
        help="Branch transferring cash from (source).",
    )
    to_branch_id = fields.Many2one(
        "havanoposdesk.store",
        string="To Branch",
        required=True,
        help="Destination branch (typically HQ or main branch).",
    )
    from_account_id = fields.Many2one(
        "havanoposdesk.account",
        string="From Account",
        domain="[('tenant_id', '=', tenant_id), ('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]",
        help="Cash/Bank account to be debited / deducted from.",
    )
    to_account_id = fields.Many2one(
        "havanoposdesk.account",
        string="To Account",
        domain="[('tenant_id', '=', tenant_id), ('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]",
        help="Cash/Bank account to receive / be credited with the cash.",
    )
    amount = fields.Monetary(
        string="Amount",
        required=True,
        currency_field="currency_id",
        help="Cash amount to transfer.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        default=lambda self: self.env.user.tenant_id.currency_id.id if self.env.user.tenant_id else self.env.ref('base.USD', raise_if_not_found=False).id,
        help="Currency for the transfer.",
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        required=True,
    )
    reason = fields.Char(
        string="Reason",
        help="Optional explanation or reason for the cash transfer (e.g. End-of-shift cash up to HQ).",
    )
    user_id = fields.Many2one(
        "res.users",
        string="Transferred By",
        default=lambda self: self.env.user.id,
        required=True,
    )
    shift_id = fields.Many2one(
        "havanoposdesk.shift",
        string="Source Shift",
        ondelete="set null",
        help="Shift from which cash is being transferred / cashed up.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        readonly=True,
    )
    state = fields.Selection([
        ("draft", "Draft"),
        ("posted", "Transferred"),
        ("cancelled", "Cancelled"),
    ], string="Status", default="draft", required=True, copy=False, tracking=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
            
            if vals.get('name', 'New') == 'New':
                if tenant and hasattr(tenant, '_get_next_sequence'):
                    vals['name'] = tenant._get_next_sequence('cash_trn')
                else:
                    # Fallback sequence in XXX-10001 format
                    seq = self.env['ir.sequence'].next_by_code('havanoposdesk.cash.transfer')
                    if not seq:
                        last = self.search([('tenant_id', '=', tenant_id)], order='id desc', limit=1)
                        next_num = (last.id + 10001) if last else 10001
                        seq = f"CTR-{next_num}"
                    vals['name'] = seq
        return super().create(vals_list)

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise ValidationError(_("The transfer amount must be greater than zero."))

    @api.constrains("from_branch_id", "to_branch_id", "from_account_id", "to_account_id")
    def _check_branches_and_accounts(self):
        for rec in self:
            if rec.from_branch_id and rec.to_branch_id and rec.from_branch_id == rec.to_branch_id:
                if rec.from_account_id and rec.to_account_id and rec.from_account_id == rec.to_account_id:
                    raise ValidationError(_("Source and destination accounts must be different when transferring within the same store."))

    @api.onchange("from_branch_id")
    def _onchange_from_branch_id(self):
        if self.from_branch_id:
            self.store_id = self.from_branch_id
            # Find default cash account matching the source branch
            account = self.env['havanoposdesk.account'].search([
                ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
                ('type', '=', 'Cash'),
                ('active', '=', True),
                '|', ('store_id', '=', self.from_branch_id.id), ('store_ids', 'in', self.from_branch_id.id)
            ], limit=1)
            if not account:
                account = self.env['havanoposdesk.account'].search([
                    ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
                    ('type', '=', 'Cash'),
                    ('active', '=', True)
                ], limit=1)
            if account:
                self.from_account_id = account.id

    @api.onchange("to_branch_id")
    def _onchange_to_branch_id(self):
        if self.to_branch_id:
            # Find default cash account matching the destination branch
            account = self.env['havanoposdesk.account'].search([
                ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
                ('type', '=', 'Cash'),
                ('active', '=', True),
                '|', ('store_id', '=', self.to_branch_id.id), ('store_ids', 'in', self.to_branch_id.id)
            ], limit=1)
            if not account:
                account = self.env['havanoposdesk.account'].search([
                    ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
                    ('type', '=', 'Cash'),
                    ('active', '=', True),
                    ('id', '!=', self.from_account_id.id if self.from_account_id else 0)
                ], limit=1)
            if account:
                self.to_account_id = account.id

    def _get_or_create_default_account(self, store, role='from'):
        """Helper to ensure an account is linked to the store/tenant."""
        account = self.env['havanoposdesk.account'].search([
            ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
            ('type', '=', 'Cash'),
            ('active', '=', True),
            '|', ('store_id', '=', store.id), ('store_ids', 'in', store.id)
        ], limit=1)
        if not account:
            account = self.env['havanoposdesk.account'].search([
                ('tenant_id', '=', self.tenant_id.id or self.env.user.tenant_id.id),
                ('type', '=', 'Cash'),
                ('active', '=', True)
            ], limit=1)
        if not account:
            account = self.env['havanoposdesk.account'].sudo().create({
                'name': f"Cash - {store.name}",
                'type': 'Cash',
                'tenant_id': self.tenant_id.id or self.env.user.tenant_id.id,
                'store_id': store.id,
                'store_ids': [(4, store.id)],
                'currency_id': store.currency_id.id or self.currency_id.id,
            })
        return account

    def action_post(self):
        """Confirm the cash transfer and update account balances."""
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Only draft transfers can be posted."))
            if rec.amount <= 0:
                raise UserError(_("Transfer amount must be greater than zero."))

            from_acc = rec.from_account_id or rec._get_or_create_default_account(rec.from_branch_id, role='from')
            to_acc = rec.to_account_id or rec._get_or_create_default_account(rec.to_branch_id, role='to')

            # Deduct from source account and add to destination account
            from_acc.sudo().balance -= rec.amount
            to_acc.sudo().balance += rec.amount

            rec.write({
                'state': 'posted',
                'from_account_id': from_acc.id,
                'to_account_id': to_acc.id,
            })
        return True

    def action_cancel(self):
        """Cancel a posted cash transfer and reverse the account balances."""
        for rec in self:
            if rec.state == 'posted':
                if rec.from_account_id:
                    rec.from_account_id.sudo().balance += rec.amount
                if rec.to_account_id:
                    rec.to_account_id.sudo().balance -= rec.amount
            rec.write({'state': 'cancelled'})
        return True

    def action_draft(self):
        """Reset transfer back to draft state."""
        for rec in self:
            if rec.state == 'posted':
                raise UserError(_("Cannot reset a posted transfer directly. Please cancel it first."))
            rec.write({'state': 'draft'})
        return True
