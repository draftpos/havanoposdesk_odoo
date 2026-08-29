import json
import logging
from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Exclude noisy or technical fields from auditing
AUDIT_IGNORED_FIELDS = {
    '__last_update', 'write_date', 'write_uid', 'create_date', 'create_uid',
    'display_name', 'message_ids', 'activity_ids', 'message_follower_ids',
    'access_token', 'access_token_signature', 'message_partner_ids',
    'rating_ids', 'website_message_ids', 'message_has_error', 'message_has_sms_error'
}


class HavanoAuditMixin(models.AbstractModel):
    _name = 'havanoposdesk.audit.mixin'
    _description = 'Havano Audit Trail Mixin'

    @api.model
    def _get_audit_request_info(self):
        ip = '127.0.0.1'
        ua = False
        method = False
        path = False
        try:
            from odoo.http import request
            if request and getattr(request, 'httprequest', None):
                hr = request.httprequest
                forwarded = hr.headers.get('X-Forwarded-For')
                if forwarded:
                    ip = forwarded.split(',')[0].strip()
                elif hr.headers.get('X-Real-IP'):
                    ip = hr.headers.get('X-Real-IP').strip()
                elif hr.remote_addr:
                    ip = hr.remote_addr

                ua = hr.headers.get('User-Agent')
                if ua and len(ua) > 250:
                    ua = ua[:247] + '...'

                method = hr.method
                path = hr.path
        except Exception:
            pass
        return {
            'ip_address': ip,
            'user_agent': ua,
            'http_method': method,
            'http_path': path,
        }

    def _format_audit_value(self, fname, val):
        if val is None or val is False:
            return ''
        if fname in self._fields:
            field = self._fields[fname]
            if field.type == 'many2one' and val:
                if isinstance(val, (int, str)) and str(val).isdigit():
                    rec = self.env[field.comodel_name].sudo().browse(int(val))
                    return rec.display_name if rec.exists() else str(val)
                elif hasattr(val, 'display_name'):
                    return val.display_name
            elif field.type == 'selection':
                selection = dict(field.get_description(self.env).get('selection', []))
                return selection.get(val, str(val))
            elif field.type == 'boolean':
                return 'Yes' if val else 'No'
            elif field.type == 'monetary' or field.type == 'float':
                return f"{float(val):,.2f}" if val is not None else '0.00'
        return str(val)

    def _create_audit_log_entry(self, action_type, record, changes_json=None, changes_summary=None, custom_user=None):
        try:
            user = custom_user or self.env.user
            tenant = getattr(record, 'tenant_id', False) or getattr(user, 'tenant_id', False)
            if not tenant and hasattr(self.env, 'user'):
                tenant = self.env.user.tenant_id
            if not tenant:
                return

            req_info = self._get_audit_request_info()
            store = getattr(record, 'store_id', False) or getattr(user, 'default_store_id', False)
            model_desc = self.env['ir.model'].sudo().search([('model', '=', self._name)], limit=1).name or self._description or self._name
            rec_name = getattr(record, 'name', False) or getattr(record, 'display_name', False) or (f"#{record.id}" if record.id else '')

            vals = {
                'timestamp': fields.Datetime.now(),
                'tenant_id': tenant.id,
                'store_id': store.id if store else False,
                'user_id': user.id if user else False,
                'user_name': user.name if user else 'System',
                'user_role': getattr(user, 'havano_role', False),
                'ip_address': req_info['ip_address'],
                'user_agent': req_info['user_agent'],
                'http_method': req_info['http_method'],
                'http_path': req_info['http_path'],
                'action_type': action_type,
                'model_name': self._name,
                'model_description': model_desc,
                'res_id': record.id if record.id else False,
                'record_name': str(rec_name),
                'changes_json': json.dumps(changes_json) if changes_json else False,
                'changes_summary': changes_summary or False,
                'active': True,
                'is_archived': False,
            }
            self.env['havanoposdesk.audit.log'].sudo().create(vals)
        except Exception as e:
            _logger.warning(f"Audit log generation failed for {self._name}: {e}")

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        if not self.env.context.get('skip_audit_log'):
            for record in records:
                try:
                    summary_lines = []
                    changes = {}
                    for k, v in record._convert_to_write(record._cache).items():
                        if k in AUDIT_IGNORED_FIELDS:
                            continue
                        field_label = self._fields[k].string if k in self._fields else k
                        formatted_v = self._format_audit_value(k, v)
                        if formatted_v:
                            changes[k] = {'label': field_label, 'new': formatted_v, 'old': None}
                            summary_lines.append(f"• {field_label}: {formatted_v}")
                    summary = "\n".join(summary_lines[:15])
                    self._create_audit_log_entry('create', record, changes_json=changes, changes_summary=summary)
                except Exception as e:
                    _logger.warning(f"Audit create hook error on {self._name}: {e}")
        return records

    def write(self, vals):
        if self.env.context.get('skip_audit_log') or not vals:
            return super().write(vals)

        # Snapshot old values for modified fields
        tracked_keys = [k for k in vals.keys() if k not in AUDIT_IGNORED_FIELDS and k in self._fields]
        old_snapshots = {}
        if tracked_keys:
            for rec in self:
                old_snapshots[rec.id] = {k: rec[k] for k in tracked_keys}

        result = super().write(vals)

        if tracked_keys:
            for rec in self:
                try:
                    old_data = old_snapshots.get(rec.id, {})
                    changes = {}
                    summary_lines = []
                    for k in tracked_keys:
                        old_v = old_data.get(k)
                        new_v = rec[k]
                        if old_v != new_v:
                            field_label = self._fields[k].string if k in self._fields else k
                            fmt_old = self._format_audit_value(k, old_v)
                            fmt_new = self._format_audit_value(k, new_v)
                            if fmt_old != fmt_new:
                                changes[k] = {'label': field_label, 'old': fmt_old, 'new': fmt_new}
                                summary_lines.append(f"• {field_label}: {fmt_old or '(empty)'}  ➔  {fmt_new or '(empty)'}")

                    if changes:
                        summary = "\n".join(summary_lines[:20])
                        self._create_audit_log_entry('write', rec, changes_json=changes, changes_summary=summary)
                except Exception as e:
                    _logger.warning(f"Audit write hook error on {self._name}: {e}")

        return result

    def unlink(self):
        if self.env.context.get('skip_audit_log'):
            return super().unlink()

        snapshots = []
        for rec in self:
            rec_name = getattr(rec, 'name', False) or getattr(rec, 'display_name', False) or f"#{rec.id}"
            snapshots.append({
                'id': rec.id,
                'name': rec_name,
                'tenant_id': getattr(rec, 'tenant_id', False) or self.env.user.tenant_id,
                'store_id': getattr(rec, 'store_id', False),
            })

        result = super().unlink()

        for snap in snapshots:
            try:
                summary = f"Deleted {self._description or self._name} '{snap['name']}' (ID: {snap['id']})"
                fake_rec = type('FakeRecord', (), {'id': snap['id'], 'name': snap['name'], 'tenant_id': snap['tenant_id'], 'store_id': snap['store_id']})()
                self._create_audit_log_entry('unlink', fake_rec, changes_summary=summary)
            except Exception as e:
                _logger.warning(f"Audit unlink hook error on {self._name}: {e}")

        return result

    def log_custom_activity(self, action_name, summary, details=None):
        """Helper to log explicit high-level business events (e.g. shift close, invoice void)."""
        self.ensure_one()
        self._create_audit_log_entry('action', self, changes_json=details, changes_summary=summary)
