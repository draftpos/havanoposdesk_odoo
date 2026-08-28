from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class Account(models.Model):
    _name = 'havanoposdesk.account'
    _description = 'Account'
    
    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Account name must be unique per tenant!')
    ]

    @api.constrains('name', 'tenant_id')
    def _check_unique_account_name(self):
        for record in self:
            if record.name and record.tenant_id:
                # Case-insensitive search for duplicates
                duplicate = self.search([
                    ('tenant_id', '=', record.tenant_id.id),
                    ('name', '=ilike', record.name),
                    ('id', '!=', record.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError("An account with the name '%s' already exists for this tenant!" % record.name)

    name = fields.Char(string='Account Name', required=True)
    active = fields.Boolean(string='Active', default=True)
    type = fields.Selection([
        ('Cash', 'Cash'),
        ('Bank', 'Bank'),
        ('Expense', 'Expense')
    ], string='Account Type', required=True)
    is_on_account = fields.Boolean(
        string='On Account',
        default=False,
        help='Silent payment mode: does not receive money or create payment entries. '
             'Sales using this mode are marked Partial. Only available for Cash accounts.'
    )
    @api.model
    def _default_currency_id(self):
        user = self.env.user
        if hasattr(user, 'tenant_id') and user.tenant_id and user.tenant_id.currency_id:
            return user.tenant_id.currency_id.id
        if hasattr(self.env, 'company') and self.env.company and self.env.company.currency_id:
            return self.env.company.currency_id.id
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        return usd.id if usd else False

    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='Currency used for this Cash or Bank account.',
        default=_default_currency_id
    )
    tenant_currency_id = fields.Many2one('res.currency', related='tenant_id.currency_id')
    balance = fields.Float(string='Balance', default=0.0)
    
    # Store reference for multi-tenancy if applicable
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    store_id = fields.Many2one('havanoposdesk.store', string='Store')
    store_ids = fields.Many2many(
        'havanoposdesk.store',
        string='Stores',
        default=lambda self: [self.env.user.default_store_id.id] if self.env.user.default_store_id else ([self.env.user.store_ids[0].id] if self.env.user.store_ids else [])
    )

    cash_transfer_from_ids = fields.One2many('havanoposdesk.cash.transfer', 'from_account_id', string='Outgoing Transfers')
    cash_transfer_to_ids = fields.One2many('havanoposdesk.cash.transfer', 'to_account_id', string='Incoming Transfers')
    cash_transfer_count = fields.Integer(string='Transfers Count', compute='_compute_cash_transfer_count')

    def _compute_cash_transfer_count(self):
        for account in self:
            account.cash_transfer_count = len(account.cash_transfer_from_ids) + len(account.cash_transfer_to_ids)

    def action_view_cash_transfers(self):
        self.ensure_one()
        return {
            'name': _('Cash Transfers - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.cash.transfer',
            'view_mode': 'list,form',
            'domain': ['|', ('from_account_id', '=', self.id), ('to_account_id', '=', self.id)],
            'context': {
                'default_from_account_id': self.id,
                'default_tenant_id': self.tenant_id.id,
            },
        }

    @api.onchange('type')
    def _onchange_type_on_account(self):
        if self.type != 'Cash':
            self.is_on_account = False
        if self.type in ('Cash', 'Bank') and not self.currency_id:
            self.currency_id = self._default_currency_id()

    @api.constrains('is_on_account', 'type')
    def _check_on_account_cash_only(self):
        for record in self:
            if record.is_on_account and record.type != 'Cash':
                raise ValidationError("On Account can only be used when Account Type is Cash.")

    @api.constrains('type', 'currency_id')
    def _check_cash_bank_currency_required(self):
        for record in self:
            if record.type in ('Cash', 'Bank') and not record.currency_id:
                raise ValidationError(_("A currency is required for Cash and Bank accounts."))

    @api.constrains('tenant_id', 'currency_id')
    def _check_currency_belongs_to_tenant(self):
        for account in self:
            if account.tenant_id and account.currency_id and account.currency_id != account.tenant_currency_id and account.currency_id.tenant_id and account.currency_id.tenant_id != account.tenant_id:
                raise ValidationError(_(
                    "Account '%s' must use a currency belonging to the same tenant."
                ) % account.name)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('tenant_id') and self.env.user.tenant_id:
                vals['tenant_id'] = self.env.user.tenant_id.id
            if vals.get('type') in ('Cash', 'Bank') and not vals.get('currency_id'):
                vals['currency_id'] = self._default_currency_id()
            tenant_id = vals.get('tenant_id')
            currency_id = vals.get('currency_id')
            if tenant_id and currency_id:
                curr = self.env['res.currency'].browse(currency_id)
                if curr and not getattr(curr, 'tenant_id', False):
                    curr.sudo().write({'tenant_id': tenant_id})
        return super().create(vals_list)

    @api.model
    def is_on_account_method(self, account=None, payment_method_name=None):
        """True for on-account modes: no receipt is posted and nothing is received."""
        if account:
            if account.is_on_account:
                return True
            names = [(account.name or ''), (payment_method_name or '')]
        else:
            names = [(payment_method_name or '')]
        for raw in names:
            name = raw.strip().lower().replace('_', ' ').replace('-', ' ')
            if name in ('on account', 'user account', 'onaccount', 'useraccount'):
                return True
            if 'on account' in name:
                return True
        return False

    def is_silent_on_account(self, payment_method_name=None):
        self.ensure_one()
        return self.is_on_account_method(self, payment_method_name)

    def action_activate(self):
        self.write({'active': True})

    def action_deactivate(self):
        self.write({'active': False})

    def action_toggle_active(self):
        for record in self:
            record.active = not record.active

