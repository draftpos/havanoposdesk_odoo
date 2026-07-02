import requests
from odoo import api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)

class HavanoErrorIssue(models.Model):
    _name = 'havano.error.issue'
    _description = 'System Error Issue'
    _order = 'last_seen desc'

    bugsink_id = fields.Char(string='Bugsink ID', required=True, index=True)
    name = fields.Char(string='Message', required=True)
    type = fields.Char(string='Type')
    first_seen = fields.Datetime(string='First Seen')
    last_seen = fields.Datetime(string='Last Seen')
    event_count = fields.Integer(string='Event Count')
    is_resolved = fields.Boolean(string='Resolved')
    transaction = fields.Char(string='Transaction')
    
    # Metadata extracted from events
    site = fields.Char(string='Site')
    user_email = fields.Char(string='User Email')
    app_release = fields.Char(string='Release')
    os_name = fields.Char(string='OS')
    
    event_ids = fields.One2many('havano.error.event', 'issue_id', string='Events')

    def _get_api_credentials(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.bugsink_base_url')
        project_id = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.bugsink_project_id')
        token = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.bugsink_api_token')
        if not base_url or not project_id or not token:
            raise UserError("Bugsink API credentials are not configured properly in Settings.")
        return base_url.rstrip('/'), project_id, token

    @api.model
    def action_sync_issues(self):
        """Fetches issues from Bugsink and updates local records."""
        base_url, project_id, token = self._get_api_credentials()
        url = f"{base_url}/api/canonical/0/issues/?project={project_id}"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            issues_data = data.get('results', [])
            
            for issue_data in issues_data:
                bugsink_id = issue_data.get('id')
                vals = {
                    'bugsink_id': bugsink_id,
                    'name': issue_data.get('calculated_value') or 'Unknown Error',
                    'type': issue_data.get('calculated_type') or 'Unknown',
                    'first_seen': issue_data.get('first_seen', '').split('.')[0].replace('T', ' ').replace('Z', ''),
                    'last_seen': issue_data.get('last_seen', '').split('.')[0].replace('T', ' ').replace('Z', ''),
                    'event_count': issue_data.get('digested_event_count', 0),
                    'is_resolved': issue_data.get('is_resolved', False),
                    'transaction': issue_data.get('transaction', ''),
                }
                
                existing = self.search([('bugsink_id', '=', bugsink_id)], limit=1)
                if existing:
                    existing.write(vals)
                else:
                    self.create(vals)
        except Exception as e:
            _logger.error(f"Failed to sync issues from Bugsink: {str(e)}")
            raise UserError(f"Failed to sync issues from Bugsink: {str(e)}")
            
    def action_sync_events(self):
        """Fetches events for the selected issues."""
        base_url, _, token = self._get_api_credentials()
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        EventModel = self.env['havano.error.event']
        
        for issue in self:
            url = f"{base_url}/api/canonical/0/events/?issue={issue.bugsink_id}"
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                data = response.json()
                events_data = data.get('results', [])
                
                for event_data in events_data[:10]: # Fetch details for top 10 recent events only
                    event_id = event_data.get('id')
                    existing_event = EventModel.search([('bugsink_id', '=', event_id)], limit=1)
                    if not existing_event:
                        # Fetch full event details to get tags and user info
                        site, release, os_name, user_email = '', '', '', ''
                        detail_url = f"{base_url}/api/canonical/0/events/{event_id}/"
                        try:
                            detail_res = requests.get(detail_url, headers=headers, timeout=10)
                            detail_res.raise_for_status()
                            full_event = detail_res.json()
                            data_payload = full_event.get('data', {})
                            tags_list = data_payload.get('tags', [])
                            
                            if isinstance(tags_list, dict):
                                tags_list = [[k, v] for k, v in tags_list.items()]
                                
                            for tag in tags_list:
                                if isinstance(tag, list) and len(tag) >= 2:
                                    k, v = tag[0], tag[1]
                                    if k == 'site': site = str(v)
                                    elif k == 'release': release = str(v)
                                    elif k == 'os.name': os_name = str(v)
                                    elif k == 'user.username': user_email = str(v)
                            
                            user_payload = data_payload.get('user', {})
                            if not user_email:
                                user_email = user_payload.get('email') or user_payload.get('username') or ''
                                
                        except Exception as e:
                            _logger.error(f"Failed to fetch details for event {event_id}: {str(e)}")

                        EventModel.create({
                            'bugsink_id': event_id,
                            'issue_id': issue.id,
                            'timestamp': event_data.get('timestamp', '').split('.')[0].replace('T', ' ').replace('Z', ''),
                            'site': site,
                            'app_release': release,
                            'os_name': os_name,
                            'user_email': user_email,
                        })
                        
                        # Update parent issue if these fields are not yet set
                        issue_vals = {}
                        if site and not issue.site: issue_vals['site'] = site
                        if release and not issue.app_release: issue_vals['app_release'] = release
                        if os_name and not issue.os_name: issue_vals['os_name'] = os_name
                        if user_email and not issue.user_email: issue_vals['user_email'] = user_email
                        if issue_vals:
                            issue.write(issue_vals)
                            
            except Exception as e:
                _logger.error(f"Failed to sync events for issue {issue.bugsink_id}: {str(e)}")

class HavanoErrorEvent(models.Model):
    _name = 'havano.error.event'
    _description = 'System Error Event'
    _order = 'timestamp desc'

    bugsink_id = fields.Char(string='Event ID', required=True, index=True)
    issue_id = fields.Many2one('havano.error.issue', string='Issue', ondelete='cascade')
    timestamp = fields.Datetime(string='Timestamp')
    stacktrace_md = fields.Text(string='Stacktrace')
    
    # Context data
    site = fields.Char(string='Site')
    user_email = fields.Char(string='User Email')
    app_release = fields.Char(string='Release')
    os_name = fields.Char(string='OS')

    def action_fetch_stacktrace(self):
        """Fetches the markdown stacktrace for the event."""
        if not self.issue_id:
            return
            
        base_url = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.bugsink_base_url')
        token = self.env['ir.config_parameter'].sudo().get_param('havanoposdesk.bugsink_api_token')
        if not base_url or not token:
            raise UserError("Bugsink API credentials are not configured properly in Settings.")
            
        base_url = base_url.rstrip('/')
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        for event in self:
            url = f"{base_url}/api/canonical/0/events/{event.bugsink_id}/"
            try:
                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                event_data = response.json()
                
                payload = event_data.get('data', {})
                stacktrace_md = ""
                
                exceptions = payload.get('exception', {}).get('values', [])
                for exc in exceptions:
                    exc_type = exc.get('type', 'Exception')
                    exc_value = exc.get('value', '')
                    stacktrace_md += f"**{exc_type}**: {exc_value}\n\n```\n"
                    
                    # Sentry formats frames from oldest to newest usually, we'll just print them as received
                    frames = exc.get('stacktrace', {}).get('frames', [])
                    for frame in reversed(frames):
                        filename = frame.get('filename', 'unknown')
                        function = frame.get('function', 'unknown')
                        lineno = frame.get('lineno', '?')
                        stacktrace_md += f"  File \"{filename}\", line {lineno}, in {function}\n"
                    stacktrace_md += "```\n\n"
                
                if not stacktrace_md:
                    stacktrace_md = "*No structured stacktrace available in event payload.*\n\n"
                    # Fallback to dump some context if no stacktrace
                    if payload.get('message'):
                        stacktrace_md += f"**Message:** {payload.get('message')}"
                        
                event.write({'stacktrace_md': stacktrace_md})
            except Exception as e:
                _logger.error(f"Failed to fetch stacktrace for event {event.bugsink_id}: {str(e)}")
                raise UserError(f"Failed to fetch stacktrace: {str(e)}")
