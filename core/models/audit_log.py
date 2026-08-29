import json
from datetime import timedelta
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HavanoAuditLog(models.Model):
    _name = 'havanoposdesk.audit.log'
    _description = 'Havano Activity & Audit Log'
    _order = 'timestamp desc, id desc'

    name = fields.Char(string='Summary', compute='_compute_name', store=True)
    timestamp = fields.Datetime(string='Date & Time', default=fields.Datetime.now, required=True, index=True, readonly=True)
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', required=True, index=True, readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store / Branch', readonly=True)
    user_id = fields.Many2one('res.users', string='User', readonly=True)
    user_name = fields.Char(string='User Name', readonly=True)
    user_role = fields.Char(string='Role', readonly=True)
    ip_address = fields.Char(string='IP Address', readonly=True, index=True)
    user_agent = fields.Char(string='Device / Browser / Client', readonly=True)
    http_method = fields.Char(string='HTTP Method', readonly=True)
    http_path = fields.Char(string='Request Endpoint', readonly=True)

    action_type = fields.Selection([
        ('create', 'Created'),
        ('write', 'Updated / Edited'),
        ('unlink', 'Deleted'),
        ('action', 'Action / Event'),
    ], string='Action', required=True, readonly=True, index=True)

    model_name = fields.Char(string='Model', required=True, readonly=True, index=True)
    model_description = fields.Char(string='Entity Type', readonly=True)
    res_id = fields.Integer(string='Record ID', readonly=True)
    record_name = fields.Char(string='Record Name / Code', readonly=True, index=True)

    changes_json = fields.Text(string='Changes Data (JSON)', readonly=True)
    changes_summary = fields.Text(string='Changes Summary', readonly=True)

    active = fields.Boolean(string='Active', default=True, index=True)
    is_archived = fields.Boolean(string='Archived', default=False, index=True)

    @api.depends('action_type', 'model_description', 'record_name')
    def _compute_name(self):
        for rec in self:
            action_map = {
                'create': _('Created'),
                'write': _('Updated'),
                'unlink': _('Deleted'),
                'action': _('Action'),
            }
            act = action_map.get(rec.action_type, _('Activity'))
            entity = rec.model_description or rec.model_name or _('Record')
            rec_str = f" '{rec.record_name}'" if rec.record_name else (f" #{rec.res_id}" if rec.res_id else '')
            rec.name = f"[{act}] {entity}{rec_str}"

    @api.model
    def _search(self, domain, offset=0, limit=None, order=None, **kwargs):
        if not self.env.su and self.env.user and getattr(self.env.user, 'tenant_id', None) and self.env.user.havano_role != 'super_admin':
            has_tenant_filter = any(isinstance(leaf, (list, tuple)) and len(leaf) > 0 and leaf[0] == 'tenant_id' for leaf in domain)
            if not has_tenant_filter:
                domain = [('tenant_id', '=', self.env.user.tenant_id.id)] + list(domain)
        return super()._search(domain, offset=offset, limit=limit, order=order, **kwargs)

    def action_archive_log(self):
        self.write({'active': False, 'is_archived': True})

    def action_unarchive_log(self):
        self.write({'active': True, 'is_archived': False})

    def unlink(self):
        # Only allow unlinking via the cleanup wizard or super admin
        if not self.env.context.get('allow_audit_log_cleanup') and self.env.user.havano_role != 'super_admin' and not self.env.su:
            raise UserError(_("Activity log entries cannot be deleted directly. Use the 'Clear / Archive Logs' wizard if needed."))
        return super().unlink()


class HavanoAuditLogClearWizard(models.TransientModel):
    _name = 'havanoposdesk.audit.log.clear.wizard'
    _description = 'Clear or Archive Activity Logs'

    tenant_id = fields.Many2one(
        'havanoposdesk.tenant',
        string='Tenant',
        default=lambda self: self.env.user.tenant_id.id if self.env.user.tenant_id else False,
        required=True,
        readonly=True
    )
    clear_mode = fields.Selection([
        ('older_30', 'Logs older than 30 days'),
        ('older_60', 'Logs older than 60 days'),
        ('older_90', 'Logs older than 90 days'),
        ('archived_only', 'All currently archived logs'),
        ('all', 'All activity logs for this workspace'),
    ], string='Filter / Range', default='older_30', required=True)

    action_mode = fields.Selection([
        ('archive', 'Archive Logs (Hide from active list view)'),
        ('purge', 'Permanently Delete Logs'),
    ], string='Action', default='archive', required=True)

    def action_process(self):
        self.ensure_one()
        domain = [('tenant_id', '=', self.tenant_id.id)]
        today = fields.Datetime.now()

        if self.clear_mode == 'older_30':
            cutoff = today - timedelta(days=30)
            domain.append(('timestamp', '<', cutoff))
        elif self.clear_mode == 'older_60':
            cutoff = today - timedelta(days=60)
            domain.append(('timestamp', '<', cutoff))
        elif self.clear_mode == 'older_90':
            cutoff = today - timedelta(days=90)
            domain.append(('timestamp', '<', cutoff))
        elif self.clear_mode == 'archived_only':
            domain.append(('is_archived', '=', True))
        elif self.clear_mode == 'all':
            pass

        logs = self.env['havanoposdesk.audit.log'].with_context(active_test=False).sudo().search(domain)
        count = len(logs)

        if not logs:
            raise UserError(_("No activity logs matched the selected criteria."))

        if self.action_mode == 'archive':
            logs.write({'active': False, 'is_archived': True})
            msg = _("Successfully archived %d activity log entries.") % count
        else:
            logs.with_context(allow_audit_log_cleanup=True).unlink()
            msg = _("Successfully deleted %d activity log entries.") % count

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Activity Logs Updated'),
                'message': msg,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }
