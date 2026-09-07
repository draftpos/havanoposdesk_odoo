from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, AccessError
import logging

_logger = logging.getLogger(__name__)


class DeleteTenantWizard(models.TransientModel):
    _name = 'wizard.delete.tenant'
    _description = 'Super Admin Delete Tenant Wizard'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant to Delete',
        required=True,
        readonly=True,
        default=lambda self: self.env.context.get('active_id')
    )
    tenant_name = fields.Char(related='tenant_id.name', string='Tenant Name', readonly=True)
    confirm_tenant_name = fields.Char(
        string='Confirm Tenant Name',
        help='Type the exact name of the tenant to confirm permanent deletion.'
    )
    acknowledge_loss = fields.Boolean(
        string='I understand that this action is permanent, non-reversible, and will erase all data for this tenant.'
    )

    users_count = fields.Integer(string='Users', compute='_compute_counts')
    stores_count = fields.Integer(string='Stores', compute='_compute_counts')
    products_count = fields.Integer(string='Products', compute='_compute_counts')
    sales_count = fields.Integer(string='Sales Orders', compute='_compute_counts')
    pos_terminals_count = fields.Integer(string='POS Terminals', compute='_compute_counts')

    @api.depends('tenant_id')
    def _compute_counts(self):
        for record in self:
            t_id = record.tenant_id.id if record.tenant_id else False
            if t_id:
                record.users_count = self.env['res.users'].sudo().search_count([
                    ('tenant_id', '=', t_id),
                    ('id', 'not in', [1, 2]),
                    ('havano_role', '!=', 'super_admin')
                ])
                record.stores_count = self.env['havanoposdesk.store'].sudo().search_count([('tenant_id', '=', t_id)])
                record.products_count = self.env['havanoposdesk.product'].sudo().search_count([('tenant_id', '=', t_id)])
                record.sales_count = self.env['havanoposdesk.sale'].sudo().search_count([('tenant_id', '=', t_id)])
                record.pos_terminals_count = self.env['havanoposdesk.pos.terminal'].sudo().search_count([('tenant_id', '=', t_id)])
            else:
                record.users_count = 0
                record.stores_count = 0
                record.products_count = 0
                record.sales_count = 0
                record.pos_terminals_count = 0

    def action_confirm_delete(self):
        self.ensure_one()

        # 1. Strict Super Admin security check
        user = self.env.user
        is_super_admin = (
            self.env.su
            or user.id == 1
            or getattr(user, 'havano_role', None) == 'super_admin'
        )
        if not is_super_admin:
            raise AccessError(_("Access Denied: Only Super Admins can delete tenants and their data."))

        if not self.tenant_id:
            raise ValidationError(_("No tenant selected for deletion."))

        # 2. Confirmation safety checks
        expected_name = (self.tenant_id.name or '').strip()
        entered_name = (self.confirm_tenant_name or '').strip()
        if entered_name != expected_name:
            raise ValidationError(
                _("Confirmation mismatch: You entered '%(entered)s', but the tenant name is '%(expected)s'. Please type the exact name to confirm.")
                % {'entered': entered_name, 'expected': expected_name}
            )

        if not self.acknowledge_loss:
            raise ValidationError(_("You must check the confirmation checkbox to proceed with deletion."))

        deleted_tenant_name = self.tenant_id.name
        _logger.warning(
            "SUPER ADMIN DELETION: Tenant '%s' (ID: %s) deletion initiated by %s (ID: %s)",
            deleted_tenant_name, self.tenant_id.id, user.login, user.id
        )

        # 3. Execute cascading deletion
        self.tenant_id.action_hard_delete_tenant_data()

        # 4. Return notification and close window
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tenant Deleted'),
                'message': _("Tenant '%s' and all associated data have been permanently deleted.") % deleted_tenant_name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
