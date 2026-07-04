from odoo import fields, models
from odoo.exceptions import ValidationError
import random
import string
import logging

_logger = logging.getLogger(__name__)


class ClearDataWizard(models.TransientModel):
    _name = 'wizard.clear.data'
    _description = 'Clear Data Wizard'

    state = fields.Selection([
        ('request', 'Request'),
        ('verify',  'Verify'),
        ('done',    'Done'),
    ], string='State', default='request')

    clear_type = fields.Selection([
        ('transactions', 'Clear Transactions Only'),
        ('all_data',     'Clear Transactions & Master Data'),
    ], string='Deletion Type', required=True, default='transactions')

    reason       = fields.Text(string='Reason for Deletion')
    confirm_loss = fields.Boolean(
        string='I understand that this will permanently delete data and it cannot be recovered.'
    )
    generated_code = fields.Char(string='Generated Code')
    entered_code   = fields.Char(string='Verification Code')
    result_log     = fields.Text(string='Deletion Report', readonly=True)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_from_email(self):
        """Return the smtp_user of the first active outgoing mail server."""
        server = self.env['ir.mail_server'].sudo().search(
            [('active', '=', True)], order='sequence asc', limit=1
        )
        return server.smtp_user if server else False

    def _send_template(self, xml_id, email_to, extra_ctx=None):
        """
        Send a mail template to *email_to*, overriding whatever the template
        has in its email_to field so the address is always resolved dynamically
        from the partner record — no hardcoding.
        """
        template = self.env.ref(xml_id, raise_if_not_found=False)
        if not template or not email_to:
            return
        email_vals = {'email_to': email_to, 'email_cc': False}
        from_email = self._get_from_email()
        if from_email:
            email_vals['email_from'] = from_email
        template.with_context(**(extra_ctx or {})).send_mail(
            self.id, force_send=True, email_values=email_vals
        )

    def _get_system_admins(self, exclude_self=False):
        """Return all active system-admin users."""
        admin_group = self.env.ref('base.group_system', raise_if_not_found=False)
        if not admin_group:
            return self.env['res.users'].browse()
        domain = [('all_group_ids', 'in', [admin_group.id]), ('active', '=', True)]
        if exclude_self:
            domain.append(('id', '!=', self.env.user.id))
        return self.env['res.users'].sudo().search(domain)

    # ── Step 1: request ──────────────────────────────────────────────────────

    def action_send_code(self):
        self.ensure_one()

        if not self.reason or len(self.reason.strip()) < 20:
            raise ValidationError(
                "Please provide a reason with at least 20 characters."
            )
        if not self.confirm_loss:
            raise ValidationError(
                "You must tick the confirmation checkbox before proceeding."
            )

        # Generate 6-digit code
        code = ''.join(random.choices(string.digits, k=6))
        self.generated_code = code
        self.state = 'verify'

        # Send code to the current user's email (from their partner record)
        user_email = self.env.user.partner_id.email
        if user_email:
            try:
                self._send_template(
                    'havanoposdesk_odoo.mail_template_clear_data_code',
                    user_email,
                )
                _logger.info("Clear data: verification code sent to %s", user_email)
            except Exception as e:
                _logger.error(
                    "Clear data: could not send code to %s: %s", user_email, e
                )
        else:
            _logger.warning(
                "Clear data: user %s has no email address — code not emailed.",
                self.env.user.login,
            )

        # Notify all OTHER system admins (best-effort)
        try:
            for admin in self._get_system_admins(exclude_self=True):
                admin_email = admin.partner_id.email
                if admin_email:
                    self._send_template(
                        'havanoposdesk_odoo.mail_template_clear_data_notify',
                        admin_email,
                        extra_ctx={'notify_admin_name': admin.name},
                    )
        except Exception as e:
            _logger.warning("Clear data: admin notification failed: %s", e)

        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }

    # ── Step 2: verify & delete ───────────────────────────────────────────────

    def action_verify_and_delete(self):
        self.ensure_one()

        if not self.entered_code:
            raise ValidationError("Please enter the verification code.")
        if self.entered_code.strip() != self.generated_code:
            raise ValidationError("Incorrect verification code. Please try again.")

        # Execute deletion and capture report
        self.result_log = self._execute_deletion()
        self.state = 'done'

        # Email completion notice to all system admins (best-effort)
        try:
            for admin in self._get_system_admins():
                admin_email = admin.partner_id.email
                if admin_email:
                    self._send_template(
                        'havanoposdesk_odoo.mail_template_clear_data_complete',
                        admin_email,
                        extra_ctx={'notify_admin_name': admin.name},
                    )
        except Exception as e:
            _logger.warning("Clear data: completion email failed: %s", e)

        # Return to the wizard so the report is visible
        return {
            'type':      'ir.actions.act_window',
            'res_model': self._name,
            'res_id':    self.id,
            'view_mode': 'form',
            'target':    'new',
        }

    def action_close(self):
        return {'type': 'ir.actions.act_window_close'}

    # ── Deletion engine ───────────────────────────────────────────────────────

    def _execute_deletion(self):
        """
        Delete records using the Odoo ORM so this method:
          • Works on ANY database where the module is installed — no hardcoded
            DB name, no hardcoded table names.
          • Auto-skips models that are not registered in this environment
            (i.e. not yet installed on a particular site).
          • Scopes deletions to the current user's tenant when they are a
            tenant-admin, so one tenant cannot wipe another tenant's data.
          • Super-admins (havano_role == 'super_admin') get an unrestricted wipe.
        """
        user = self.env.user
        log  = []

        _logger.warning(
            "Data wipe: initiated by %s (%s) | type=%s | reason=%s",
            user.name, user.login, self.clear_type, self.reason,
        )

        # ── Tenant scope ─────────────────────────────────────────────────────
        havano_role = getattr(user, 'havano_role', False)
        tenant      = getattr(user, 'tenant_id', False)

        if havano_role == 'super_admin' or not tenant:
            # Super-admin: wipe everything across all tenants
            base_domain = []
            scope_label = "All tenants (super-admin)"
        else:
            # Tenant admin: restrict to their own tenant only
            base_domain = [('tenant_id', '=', tenant.id)]
            scope_label = f"Tenant: {tenant.name}"

        # ── ORM delete helper ─────────────────────────────────────────────────
        def orm_delete(label, model_name, extra_domain=None):
            """
            Delete records of *model_name* using self.env (current DB, current
            registry).  Silently skips if the model is not installed on this site.
            """
            # Check model is available in this Odoo instance / database
            if model_name not in self.env:
                return  # not installed here — skip without logging noise

            domain = list(base_domain)
            if extra_domain:
                domain += extra_domain

            try:
                records = self.env[model_name].sudo().search(domain)
                count   = len(records)
                if count:
                    records.unlink()
                log.append(
                    f"  {'✓' if count else '–'}  {label:<35s} {count:>5} record(s)"
                )
            except Exception as e:
                _logger.error("orm_delete %s: %s", model_name, e)
                log.append(f"  ⚠  {label:<35s} ERROR — {e}")

        # ── Transactions ──────────────────────────────────────────────────────
        log.append("═" * 52)
        log.append("  TRANSACTIONS")
        log.append("═" * 52)

        # Child records must come before parent records (FK order)
        orm_delete("Sale lines",              "havanoposdesk.sale.line")
        orm_delete("Sales",                   "havanoposdesk.sale")
        orm_delete("Purchase lines",          "havanoposdesk.purchase.line")
        orm_delete("Purchases",               "havanoposdesk.purchase")
        orm_delete("Stock adjustment lines",  "havanoposdesk.stock.adjustment.line")
        orm_delete("Stock adjustments",       "havanoposdesk.stock.adjustment")
        orm_delete("Stock valuation",         "havanoposdesk.stock.valuation")
        orm_delete("Stock ledger",            "havanoposdesk.stock.ledger")
        orm_delete("Payments",                "havanoposdesk.payment")
        orm_delete("Accounts",                "havanoposdesk.account")
        orm_delete("Expenses",                "havanoposdesk.expense")
        orm_delete("Product costing history", "havanoposdesk.product.costing")

        # ── Master data (only when user chose 'all_data') ─────────────────────
        if self.clear_type == 'all_data':
            log.append("")
            log.append("═" * 52)
            log.append("  MASTER DATA")
            log.append("═" * 52)

            orm_delete("Customers",          "havanoposdesk.customer")
            orm_delete("Suppliers",          "havanoposdesk.supplier")
            orm_delete("Products",           "havanoposdesk.product")
            orm_delete("Categories",         "havanoposdesk.category")
            orm_delete("Units of measure",   "havanoposdesk.uom")

        # ── Summary footer ────────────────────────────────────────────────────
        type_label = dict(self._fields['clear_type'].selection)[self.clear_type]
        log.append("")
        log.append("═" * 52)
        log.append(f"  Completed by : {user.name} ({user.login})")
        log.append(f"  Type         : {type_label}")
        log.append(f"  Scope        : {scope_label}")
        log.append("═" * 52)

        return "\n".join(log)
