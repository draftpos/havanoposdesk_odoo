from odoo import models, fields, api
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
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        help='Currency used for this Cash or Bank account.',
        default=lambda self: self.env.user.tenant_id.currency_id.id or self.env.ref('base.USD', raise_if_not_found=False).id
    )
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

    @api.onchange('type')
    def _onchange_type_on_account(self):
        if self.type != 'Cash':
            self.is_on_account = False

    @api.constrains('is_on_account', 'type')
    def _check_on_account_cash_only(self):
        for record in self:
            if record.is_on_account and record.type != 'Cash':
                raise ValidationError("On Account can only be used when Account Type is Cash.")

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

