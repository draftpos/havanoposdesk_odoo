import logging
from odoo import models, fields, api, _
from datetime import datetime, timedelta, date

_logger = logging.getLogger(__name__)


class HavanoOnlineActivity(models.Model):
    _name = 'havanoposdesk.online.activity'
    _description = 'Online Activity & Device Availability Tracker'
    _order = 'last_activity desc, id desc'

    name = fields.Char(string='Activity Description', compute='_compute_name', store=True)
    user_id = fields.Many2one('res.users', string='User', index=True)
    user_name = fields.Char(related='user_id.name', string='User Name', store=True, readonly=True)
    user_login = fields.Char(related='user_id.login', string='Login / Email', store=True, readonly=True)
    havano_role = fields.Selection(related='user_id.havano_role', string='Role', store=True, readonly=True)

    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', index=True, required=True)
    tenant_ref_id = fields.Integer(related='tenant_id.id', string='Tenant ID', store=True, readonly=True)
    store_id = fields.Many2one('havanoposdesk.store', string='Store', index=True)
    store_name = fields.Char(related='store_id.name', string='Store Name', store=True, readonly=True)
    admin_name = fields.Char(related='tenant_id.admin_name', string='Admin Name', store=True, readonly=True)
    email = fields.Char(related='tenant_id.email', string='Email', store=True, readonly=True)
    phone = fields.Char(related='tenant_id.phone', string='Phone', store=True, readonly=True)
    address = fields.Text(related='tenant_id.address', string='Address', store=True, readonly=True)
    city = fields.Char(related='tenant_id.city', string='City', store=True, readonly=True)
    sales_rep = fields.Char(related='tenant_id.sales_rep', string='Sales Rep', store=True, readonly=True)
    technician = fields.Char(related='tenant_id.technician', string='Technician', store=True, readonly=True)
    owner_whatsapp = fields.Char(related='tenant_id.owner_whatsapp', string='V. WhatsApp', store=True, readonly=True)
    terminal_id = fields.Many2one('havanoposdesk.pos.terminal', string='POS Terminal', index=True)
    device_hardware_id = fields.Char(string='Hardware ID', index=True)
    device_name = fields.Char(string='Device Name', compute='_compute_device_info', store=True)
    app_version = fields.Char(string='App Version')
    platform = fields.Selection([
        ('mobile_pos', 'Mobile POS (Flutter)'),
        ('desktop_pos', 'Desktop POS'),
        ('web', 'Web Browser')
    ], string='Platform', default='mobile_pos')
    ip_address = fields.Char(string='IP Address')

    login_time = fields.Datetime(string='Logged In At', default=fields.Datetime.now)
    last_activity = fields.Datetime(string='Last Activity / Seen', default=fields.Datetime.now, index=True)
    last_activity_date = fields.Date(string='Last Activity Date', compute='_compute_activity_date', store=True, index=True)

    is_online = fields.Boolean(string='Is Online', compute='_compute_status', store=True, index=True)
    online_status = fields.Selection([
        ('online', 'Online'),
        ('idle', 'Idle (5-15m)'),
        ('offline', 'Offline')
    ], string='Status', compute='_compute_status', store=True, index=True)

    online_duration_seconds = fields.Float(string='Online Seconds', default=0.0)
    online_duration_display = fields.Char(string='Usage / Time Online', compute='_compute_duration_display')

    days_inactive = fields.Integer(string='Days Inactive', compute='_compute_days_inactive', store=True, index=True)
    days_inactive_display = fields.Char(string='Inactive Duration', compute='_compute_days_inactive_display')

    active = fields.Boolean(string='Active', default=True)

    @api.depends('user_id', 'terminal_id', 'device_hardware_id', 'tenant_id')
    def _compute_name(self):
        for rec in self:
            u_name = rec.user_id.name or rec.user_login or 'Unknown User'
            t_name = rec.tenant_id.name or 'Tenant'
            term_name = rec.terminal_id.name or (f"HW {rec.device_hardware_id[:8]}" if rec.device_hardware_id else (rec.platform or 'Device'))
            rec.name = f"{t_name} | {u_name} ({term_name})"

    @api.depends('terminal_id', 'terminal_id.name', 'device_hardware_id', 'platform')
    def _compute_device_info(self):
        for rec in self:
            if rec.terminal_id:
                rec.device_name = rec.terminal_id.name
            elif rec.device_hardware_id:
                rec.device_name = f"Hardware {rec.device_hardware_id[:10]}"
            elif rec.platform == 'web':
                rec.device_name = "Web Client"
            else:
                rec.device_name = "POS Client"

    @api.depends('last_activity')
    def _compute_activity_date(self):
        for rec in self:
            rec.last_activity_date = rec.last_activity.date() if rec.last_activity else False

    @api.depends('last_activity')
    def _compute_status(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.last_activity:
                rec.is_online = False
                rec.online_status = 'offline'
                continue
            delta = (now - rec.last_activity).total_seconds()
            if delta <= 1800:  # <= 30 minutes
                rec.is_online = True
                rec.online_status = 'online'
            elif delta <= 3600:  # 30 - 60 minutes
                rec.is_online = False
                rec.online_status = 'idle'
            else:
                rec.is_online = False
                rec.online_status = 'offline'

    @api.depends('online_duration_seconds', 'login_time', 'last_activity', 'is_online')
    def _compute_duration_display(self):
        for rec in self:
            secs = rec.online_duration_seconds or 0.0
            if rec.login_time and rec.last_activity:
                diff = (rec.last_activity - rec.login_time).total_seconds()
                if diff > secs:
                    secs = diff
            if secs < 60:
                rec.online_duration_display = f"{int(secs)}s" if secs > 0 else "< 1 min"
            elif secs < 3600:
                mins = int(secs // 60)
                rec.online_duration_display = f"{mins} min{'s' if mins > 1 else ''}"
            else:
                hrs = int(secs // 3600)
                mins = int((secs % 3600) // 60)
                rec.online_duration_display = f"{hrs}h {mins}m"

    @api.depends('last_activity')
    def _compute_days_inactive(self):
        today = date.today()
        for rec in self:
            if not rec.last_activity:
                rec.days_inactive = 9999
            else:
                act_date = rec.last_activity.date()
                diff = (today - act_date).days
                rec.days_inactive = max(0, diff)

    @api.depends('days_inactive', 'last_activity', 'is_online')
    def _compute_days_inactive_display(self):
        now = fields.Datetime.now()
        for rec in self:
            if not rec.last_activity:
                rec.days_inactive_display = "Never Used"
                continue
            delta = (now - rec.last_activity).total_seconds()
            if rec.is_online and delta <= 1800:
                rec.days_inactive_display = "Active Now"
            elif rec.days_inactive == 0:
                rec.days_inactive_display = "Used Today"
            elif rec.days_inactive == 1:
                rec.days_inactive_display = "Yesterday (1 day ago)"
            elif rec.days_inactive < 30:
                rec.days_inactive_display = f"{rec.days_inactive} days ago"
            else:
                months = rec.days_inactive // 30
                rec.days_inactive_display = f"{months} month{'s' if months > 1 else ''} ago"

    @api.model
    def record_activity(self, user=None, tenant=None, store=None, terminal=None,
                        device_hardware_id=None, app_version=None, platform='mobile_pos', ip_address=None):
        """Update or create active session/device tracker record."""
        now = fields.Datetime.now()
        user_id = user.id if user else (self.env.user.id if self.env.user.id != self.env.ref('base.public_user').id else False)
        tenant_id = (tenant.id if tenant else False) or (user.tenant_id.id if user and getattr(user, 'tenant_id', None) else False) or self.env.user.tenant_id.id

        if not tenant_id:
            first_tenant = self.env['havanoposdesk.tenant'].sudo().search([], limit=1)
            tenant_id = first_tenant.id if first_tenant else False

        if not tenant_id:
            return False

        store_id = (store.id if store else False) or (terminal.store_id.id if terminal and getattr(terminal, 'store_id', None) else False)
        terminal_id = terminal.id if terminal else False

        domain = [('tenant_id', '=', tenant_id)]
        if terminal_id:
            domain.append(('terminal_id', '=', terminal_id))
        elif device_hardware_id:
            domain.append(('device_hardware_id', '=', device_hardware_id))
        elif user_id:
            domain.append(('user_id', '=', user_id))
            domain.append(('platform', '=', platform))

        existing = self.sudo().search(domain, order='last_activity desc', limit=1)
        if existing:
            vals = {'last_activity': now}
            if user_id and existing.user_id.id != user_id:
                vals['user_id'] = user_id
            if store_id and existing.store_id.id != store_id:
                vals['store_id'] = store_id
            if terminal_id and existing.terminal_id.id != terminal_id:
                vals['terminal_id'] = terminal_id
            if app_version and existing.app_version != app_version:
                vals['app_version'] = app_version
            if ip_address:
                vals['ip_address'] = ip_address

            delta = (now - existing.last_activity).total_seconds() if existing.last_activity else 0
            if 0 < delta < 14400:
                vals['online_duration_seconds'] = existing.online_duration_seconds + min(delta, 300)
            elif delta >= 14400:
                vals['login_time'] = now
                vals['online_duration_seconds'] = 0.0

            existing.write(vals)
            return existing
        else:
            vals = {
                'tenant_id': tenant_id,
                'store_id': store_id,
                'user_id': user_id,
                'terminal_id': terminal_id,
                'device_hardware_id': device_hardware_id,
                'app_version': app_version,
                'platform': platform,
                'ip_address': ip_address,
                'login_time': now,
                'last_activity': now,
                'online_duration_seconds': 0.0,
            }
            return self.sudo().create(vals)

    @api.model
    def sync_historical_activities(self):
        """Initial bootstrap: populates tracking records from existing res.users.log and terminals."""
        Users = self.env['res.users'].sudo()
        Terminals = self.env['havanoposdesk.pos.terminal'].sudo()

        # 1. Sync from Users
        users = Users.search([('active', '=', True)])
        for u in users:
            if not u.tenant_id:
                continue
            exist = self.search([('user_id', '=', u.id), ('tenant_id', '=', u.tenant_id.id)], limit=1)
            login_dt = u.login_date or u.create_date
            if not exist:
                self.create({
                    'tenant_id': u.tenant_id.id,
                    'store_id': u.default_store_id.id if getattr(u, 'default_store_id', None) else False,
                    'user_id': u.id,
                    'platform': 'web' if u.havano_role in ('super_admin', 'admin') else 'mobile_pos',
                    'login_time': login_dt,
                    'last_activity': login_dt,
                })
            else:
                if login_dt and (not exist.last_activity or login_dt > exist.last_activity):
                    exist.write({'last_activity': login_dt, 'login_time': login_dt})

        # 2. Sync from Terminals
        terminals = Terminals.search([('active', '=', True)])
        for term in terminals:
            if not term.tenant_id:
                continue
            exist = self.search([('terminal_id', '=', term.id)], limit=1)
            last_seen = term.last_seen or term.create_date
            if not exist:
                self.create({
                    'tenant_id': term.tenant_id.id,
                    'store_id': term.store_id.id if term.store_id else False,
                    'terminal_id': term.id,
                    'user_id': term.last_logged_in_user_id.id if term.last_logged_in_user_id else False,
                    'device_hardware_id': term.device_hardware_id,
                    'app_version': term.app_version,
                    'platform': 'mobile_pos',
                    'login_time': last_seen,
                    'last_activity': last_seen,
                })
            else:
                vals = {}
                if term.device_hardware_id and not exist.device_hardware_id:
                    vals['device_hardware_id'] = term.device_hardware_id
                if term.app_version and not exist.app_version:
                    vals['app_version'] = term.app_version
                if last_seen and (not exist.last_activity or last_seen > exist.last_activity):
                    vals['last_activity'] = last_seen
                if vals:
                    exist.write(vals)

        # 3. Ensure every Tenant has at least one activity tracking record
        Tenants = self.env['havanoposdesk.tenant'].sudo().search([])
        AuditLogs = self.env['havanoposdesk.audit.log'].sudo()
        Sales = self.env['havanoposdesk.sale'].sudo()
        for t in Tenants:
            exist = self.search([('tenant_id', '=', t.id)], limit=1)
            if not exist:
                last_time = None
                user_id = False
                last_log = AuditLogs.search([('tenant_id', '=', t.id)], order='timestamp desc', limit=1)
                if last_log and last_log.timestamp:
                    last_time = last_log.timestamp
                    user_id = last_log.user_id.id if last_log.user_id else False
                if not last_time:
                    last_sale = Sales.search([('tenant_id', '=', t.id)], order='date_order desc', limit=1)
                    if last_sale and last_sale.date_order:
                        last_time = last_sale.date_order
                        user_id = last_sale.user_id.id if getattr(last_sale, 'user_id', None) else False
                if not last_time:
                    last_time = t.create_date or fields.Datetime.now()
                if not user_id and t.user_ids:
                    user_id = t.user_ids[0].id

                store_id = t.store_ids[0].id if getattr(t, 'store_ids', None) and t.store_ids else False
                self.create({
                    'tenant_id': t.id,
                    'store_id': store_id,
                    'user_id': user_id,
                    'platform': 'desktop_pos',
                    'login_time': last_time,
                    'last_activity': last_time,
                })

        return True

    @api.model
    def web_search_read(self, *args, **kwargs):
        if self.sudo().search_count([]) == 0:
            try:
                self.sudo().sync_historical_activities()
            except Exception:
                pass
        return super().web_search_read(*args, **kwargs)

    @api.model
    def _cron_update_activity_statuses(self):
        """Cron job to update days inactive and status periodically."""
        now = fields.Datetime.now()
        thirty_mins_ago = now - timedelta(minutes=30)
        sixty_mins_ago = now - timedelta(minutes=60)

        # 1. Sync latest last_seen from POS terminals if newer
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("""
                    UPDATE havanoposdesk_online_activity a
                    SET last_activity = t.last_seen
                    FROM havanoposdesk_pos_terminal t
                    WHERE a.terminal_id = t.id
                      AND t.last_seen IS NOT NULL
                      AND (a.last_activity IS NULL OR t.last_seen > a.last_activity);
                """)
        except Exception as e:
            _logger.warning("Error syncing terminal last_seen in cron: %s", e)

        # 2. Update is_online and online_status based on the 30-minute window
        try:
            with self.env.cr.savepoint():
                self.env.cr.execute("""
                    UPDATE havanoposdesk_online_activity
                    SET is_online = CASE 
                            WHEN last_activity >= %s THEN TRUE 
                            ELSE FALSE 
                        END,
                        online_status = CASE 
                            WHEN last_activity IS NULL THEN 'offline'
                            WHEN last_activity >= %s THEN 'online'
                            WHEN last_activity >= %s THEN 'idle'
                            ELSE 'offline'
                        END,
                        days_inactive = CASE
                            WHEN last_activity IS NULL THEN 9999
                            ELSE GREATEST(0, (CURRENT_DATE - (last_activity AT TIME ZONE 'UTC')::date))
                        END;
                """, (thirty_mins_ago, thirty_mins_ago, sixty_mins_ago))
        except Exception as e:
            _logger.warning("Error updating online activity statuses in cron: %s", e)
