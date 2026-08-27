from odoo import fields, models, api

class CashTransfer(models.Model):
    _name = "havanoposdesk.cash.transfer"
    _description = "Cash Transfer between branches"
    _order = "date desc"

    tenant_id = fields.Many2one(
        "havanoposdesk.tenant",
        string="Tenant",
        default=lambda self: self.env.user.tenant_id.id,
        index=True,
        readonly=True,
    )

    store_id = fields.Many2one(
        "havanoposdesk.store",
        string="Store",
        required=True,
        help="Store where the cash is currently held (source).",
    )
    from_branch_id = fields.Many2one(
        "havanoposdesk.store",
        string="From Branch",
        required=True,
        help="Branch the cash is transferred from.",
    )
    to_branch_id = fields.Many2one(
        "havanoposdesk.store",
        string="To Branch",
        required=True,
        help="Destination branch (typically HQ).",
    )
    amount = fields.Monetary(
        string="Amount",
        required=True,
        help="Cash amount to transfer.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        string="Currency",
        related="store_id.currency_id",
        readonly=True,
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        required=True,
    )
    reason = fields.Char(
        string="Reason",
        help="Optional free‑text explanation for the transfer.",
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
        readonly=True,
    )

    @api.constrains("amount")
    def _check_amount_positive(self):
        for rec in self:
            if rec.amount <= 0:
                raise models.ValidationError("The transfer amount must be greater than zero.")
