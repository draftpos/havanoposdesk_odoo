from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class Expense(models.Model):
    _name = 'havanoposdesk.expense'
    _description = 'Expense'

    _sql_constraints = [
        ('name_tenant_uniq', 'unique (name, tenant_id)', 'Expense name must be unique per tenant!')
    ]

    name = fields.Char(string='Reference', required=True, copy=False, readonly=True, default=lambda self: 'New')
    date = fields.Date(string='Date', default=fields.Date.context_today, required=True)
    account_id = fields.Many2one('havanoposdesk.account', string='Expense Account', domain=[('type', '=', 'Expense'), ('active', '=', True)], required=True)
    amount = fields.Float(string='Amount', required=True)
    description = fields.Text(string='Description')
    supplier_id = fields.Many2one('havanoposdesk.supplier', string='Supplier')
    is_paid = fields.Boolean(string='Paid')
    payment_account_id = fields.Many2one(
        'havanoposdesk.account', 
        string='Payment Account', 
        domain="[('type', 'in', ['Cash', 'Bank']), ('active', '=', True)]"
    )
    state = fields.Selection([
        ('Draft', 'Draft'),
        ('Pending', 'Pending Approval'),
        ('Posted', 'Posted'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled')
    ], string='Status', readonly=True, default='Draft')

    submitted_by_cashier = fields.Boolean(
        string='Submitted by Cashier',
        default=False,
        help='If True, this expense was submitted from the POS by a cashier and may require approval.'
    )

    shift_id = fields.Many2one('havanoposdesk.shift', string='Shift', copy=False)
    
    # Store reference
    tenant_id = fields.Many2one(
        'havanoposdesk.tenant', 
        string='Tenant', 
        required=True, 
        default=lambda self: self.env.user.tenant_id.id or (self.env['havanoposdesk.tenant'].search([], limit=1) or self.env['havanoposdesk.tenant'].create({'name': 'Default Tenant'})).id
    )
    def _default_store_id(self):
        store = self.env['havanoposdesk.store'].search([('is_default', '=', True)], limit=1)
        if not store and self.env.user.tenant_id:
            store = self.env['havanoposdesk.store'].search([('tenant_id', '=', self.env.user.tenant_id.id)], limit=1)
        return store.id if store else False

    store_id = fields.Many2one('havanoposdesk.store', string='Store', default=_default_store_id)
    currency_id = fields.Many2one('res.currency', related='store_id.currency_id', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('shift_id'):
                open_shift = self.env['havanoposdesk.shift'].search([
                    ('user_id', '=', self.env.user.id),
                    ('state', '=', 'open')
                ], limit=1)
                if open_shift:
                    vals['shift_id'] = open_shift.id

            tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
            if tenant_id:
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id)
                if tenant and not tenant.check_subscription_active():
                    raise ValidationError(_("Your subscription has expired and the grace period has ended. Please upgrade your package to resume operations."))

            if vals.get('name', 'New') == 'New':
                tenant_id = vals.get('tenant_id') or self.env.user.tenant_id.id
                tenant = self.env['havanoposdesk.tenant'].browse(tenant_id) if tenant_id else self.env['havanoposdesk.tenant']
                if tenant:
                    vals['name'] = tenant._get_next_sequence('exp')
                else:
                    vals['name'] = self.env['ir.sequence'].next_by_code('havanoposdesk.expense') or 'New'
        return super().create(vals_list)

    def write(self, vals):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state not in ('Draft', 'Pending') and any(f not in ['state'] for f in vals.keys()):
                raise ValidationError("You cannot modify a confirmed/posted expense. Please cancel it first.")
        return super().write(vals)

    def unlink(self):
        from odoo.exceptions import ValidationError
        for record in self:
            if record.state not in ('Draft', 'Pending', 'Rejected'):
                raise ValidationError("You cannot delete a confirmed/posted expense. Please cancel it first.")
        return super().unlink()

    def action_submit_for_approval(self):
        """Submit expense for manager approval. Called from POS when approval is required."""
        for record in self:
            if record.state == 'Draft':
                record.state = 'Pending'

    def action_approve(self):
        """Approve a pending expense — posts it and deducts cash."""
        for record in self:
            if record.state == 'Pending':
                record.action_post()

    def action_reject(self):
        """Reject a pending expense — no cash is deducted."""
        for record in self:
            if record.state == 'Pending':
                record.state = 'Rejected'

    def action_post(self):
        for record in self:
            if record.state in ('Draft', 'Pending'):
                if record.is_paid:
                    if not record.payment_account_id:
                        from odoo.exceptions import ValidationError
                        raise ValidationError("Please select a Payment Account for paid expenses.")
                    # Subtract from payment account (cash/bank) using sudo()
                    record.payment_account_id.sudo().balance -= record.amount
                    # Add to expense account using sudo()
                    record.account_id.sudo().balance += record.amount
                else:
                    # Just add to expense account if not paid using sudo()
                    record.account_id.sudo().balance += record.amount
                record.state = 'Posted'

    def action_cancel(self):
        for record in self:
            if record.state not in ('Posted',):
                continue
            if record.is_paid and record.payment_account_id:
                # Reverse subtraction using sudo()
                record.payment_account_id.sudo().balance += record.amount
                # Reverse addition using sudo()
                record.account_id.sudo().balance -= record.amount
            else:
                # Reverse addition using sudo()
                record.account_id.sudo().balance -= record.amount
            record.state = 'Cancelled'

    def action_draft(self):
        for record in self:
            if record.state not in ('Cancelled', 'Rejected'):
                continue
            record.state = 'Draft'
