import requests
from odoo import api, fields, models
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


def _clean_dt(raw):
    """Strip microseconds and normalise ISO timestamp to Odoo-friendly string."""
    if not raw:
        return False
    return raw.split('.')[0].replace('T', ' ').replace('Z', '')


def _parse_tags(tags_raw):
    """
    Bugsink returns tags as either:
      - a list of [key, value] pairs
      - a dict {key: value}
    Returns a plain dict {key: value}.
    """
    if not tags_raw:
        return {}
    if isinstance(tags_raw, dict):
        return {str(k): str(v) for k, v in tags_raw.items()}
    result = {}
    for item in tags_raw:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            result[str(item[0])] = str(item[1])
    return result


class HavanoErrorIssue(models.Model):
    _name = 'havano.error.issue'
    _description = 'System Error Issue'
    _order = 'last_seen desc'

    # ── Core Bugsink fields ──────────────────────────────────────────────────
    bugsink_id = fields.Char(string='Bugsink ID', required=True, index=True)
    name = fields.Char(string='Message', required=True)
    type = fields.Char(string='Error Type')
    first_seen = fields.Datetime(string='First Seen')
    last_seen = fields.Datetime(string='Last Seen')
    event_count = fields.Integer(string='Total Events')
    stored_event_count = fields.Integer(string='Stored Events')
    is_resolved = fields.Boolean(string='Resolved')
    transaction = fields.Char(string='Transaction')

    # ── Rich metadata extracted from events ──────────────────────────────────
    site = fields.Char(string='Site')
    user_email = fields.Char(string='User Email')
    app_release = fields.Char(string='Release')
    os_name = fields.Char(string='OS')
    environment = fields.Char(string='Environment')      # production / development
    error_category = fields.Char(string='Error Category') # e.g. admin, user
    operation = fields.Char(string='Operation')           # e.g. "Sync Sales Invoice"
    current_screen = fields.Char(string='Current Screen')
    event_origin = fields.Char(string='Origin')           # flutter, dart, etc.

    event_ids = fields.One2many('havano.error.event', 'issue_id', string='Events')

    # ── Helpers ──────────────────────────────────────────────────────────────
    def _get_api_credentials(self):
        icp = self.env['ir.config_parameter'].sudo()
        base_url = icp.get_param('havanoposdesk.bugsink_base_url')
        project_id = icp.get_param('havanoposdesk.bugsink_project_id')
        token = icp.get_param('havanoposdesk.bugsink_api_token')
        if not base_url or not project_id or not token:
            raise UserError("Bugsink API credentials are not configured properly in Settings.")
        return base_url.rstrip('/'), project_id, token

    def _get_headers(self, token):
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

    def _fetch_all_pages(self, url, headers):
        """Follow Bugsink cursor pagination and return all results."""
        results = []
        while url:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                results.extend(data.get('results', []))
                url = data.get('next')  # cursor-based next page URL or null
            except Exception as e:
                _logger.error(f"Pagination fetch failed at {url}: {e}")
                break
        return results

    # ── Sync Issues ──────────────────────────────────────────────────────────
    def action_sync_issues(self):
        """Fetches ALL issues (with pagination) from Bugsink and upserts local records."""
        base_url, project_id, token = self._get_api_credentials()
        headers = self._get_headers(token)
        url = f"{base_url}/api/canonical/0/issues/?project={project_id}&order=desc"

        try:
            issues_data = self._fetch_all_pages(url, headers)
            synced = 0
            for issue_data in issues_data:
                bugsink_id = issue_data.get('id')
                if not bugsink_id:
                    continue

                vals = {
                    'bugsink_id': bugsink_id,
                    'name': issue_data.get('calculated_value') or 'Unknown Error',
                    'type': issue_data.get('calculated_type') or 'Unknown',
                    'first_seen': _clean_dt(issue_data.get('first_seen')),
                    'last_seen': _clean_dt(issue_data.get('last_seen')),
                    'event_count': issue_data.get('digested_event_count', 0),
                    'stored_event_count': issue_data.get('stored_event_count', 0),
                    'is_resolved': issue_data.get('is_resolved', False),
                    'transaction': issue_data.get('transaction') or '',
                }

                existing = self.search([('bugsink_id', '=', bugsink_id)], limit=1)
                if existing:
                    existing.write(vals)
                else:
                    self.create(vals)
                synced += 1

            _logger.info(f"Bugsink sync: upserted {synced} issues.")
        except Exception as e:
            _logger.error(f"Failed to sync issues from Bugsink: {e}")
            raise UserError(f"Failed to sync issues from Bugsink: {e}")

    # ── Sync Events ──────────────────────────────────────────────────────────
    def action_sync_events(self):
        """
        For each selected issue, fetches the most recent events and enriches
        both the Event and the Issue with all available tag metadata.
        """
        base_url, _, token = self._get_api_credentials()
        headers = self._get_headers(token)
        EventModel = self.env['havano.error.event']

        for issue in self:
            url = f"{base_url}/api/canonical/0/events/?issue={issue.bugsink_id}&order=desc"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                events_data = resp.json().get('results', [])

                # Enrich top 10 most-recent events only to limit API calls
                for event_data in events_data[:10]:
                    event_id = event_data.get('id')
                    if not event_id:
                        continue

                    existing_event = EventModel.search([('bugsink_id', '=', event_id)], limit=1)
                    
                    # Skip if already cached AND has metadata populated
                    if existing_event and (existing_event.site or existing_event.app_release or existing_event.environment):
                        continue

                    # ── Fetch full event detail (includes `data` + `stacktrace_md`) ──
                    tags = {}
                    stacktrace_md = ''
                    user_email = ''
                    detail_url = f"{base_url}/api/canonical/0/events/{event_id}/"
                    try:
                        detail_resp = requests.get(detail_url, headers=headers, timeout=15)
                        detail_resp.raise_for_status()
                        full_event = detail_resp.json()

                        # Use Bugsink's pre-rendered stacktrace if available
                        stacktrace_md = full_event.get('stacktrace_md') or ''

                        data_payload = full_event.get('data') or {}

                        # ── Parse all tags ──────────────────────────────────
                        tags = _parse_tags(data_payload.get('tags', []))
                        _logger.info(f"Bugsink event {event_id} tags: {tags}")

                        # ── User info ────────────────────────────────────────
                        user_payload = data_payload.get('user') or {}
                        user_email = (
                            tags.get('user.username')
                            or user_payload.get('email')
                            or user_payload.get('username')
                            or ''
                        )

                        # ── Build stacktrace from exception frames if needed ──
                        if not stacktrace_md:
                            exceptions = data_payload.get('exception', {}).get('values', [])
                            lines = []
                            for exc in exceptions:
                                exc_type = exc.get('type', 'Exception')
                                exc_value = exc.get('value', '')
                                lines.append(f"**{exc_type}**: {exc_value}\n\n```")
                                frames = exc.get('stacktrace', {}).get('frames', [])
                                for frame in reversed(frames):
                                    fn = frame.get('filename', 'unknown')
                                    func = frame.get('function', 'unknown')
                                    ln = frame.get('lineno', '?')
                                    lines.append(f'  File "{fn}", line {ln}, in {func}')
                                lines.append("```\n")
                            stacktrace_md = '\n'.join(lines) or '*No stacktrace available.*'

                    except Exception as ex:
                        _logger.error(f"Failed to fetch detail for event {event_id}: {ex}")

                    # ── Create or update the Event record ───────────────────
                    event_vals = {
                        'bugsink_id': event_id,
                        'issue_id': issue.id,
                        'timestamp': _clean_dt(event_data.get('timestamp')),
                        'stacktrace_md': stacktrace_md,
                        'site': tags.get('site', ''),
                        'app_release': tags.get('release', ''),
                        'os_name': tags.get('os.name', ''),
                        'user_email': user_email,
                        'environment': tags.get('environment', ''),
                        'error_category': tags.get('error_category', ''),
                        'operation': tags.get('operation', ''),
                        'current_screen': tags.get('current_screen', ''),
                        'event_origin': tags.get('event.origin', ''),
                    }
                    if existing_event:
                        existing_event.write(event_vals)
                    else:
                        EventModel.create(event_vals)

                    # ── Backfill Issue metadata from the first event seen ────
                    issue_update = {}
                    def _backfill(field, val):
                        if val and not getattr(issue, field):
                            issue_update[field] = val
                    _backfill('site', tags.get('site', ''))
                    _backfill('app_release', tags.get('release', ''))
                    _backfill('os_name', tags.get('os.name', ''))
                    _backfill('user_email', user_email)
                    _backfill('environment', tags.get('environment', ''))
                    _backfill('error_category', tags.get('error_category', ''))
                    _backfill('operation', tags.get('operation', ''))
                    _backfill('current_screen', tags.get('current_screen', ''))
                    _backfill('event_origin', tags.get('event.origin', ''))
                    if issue_update:
                        issue.write(issue_update)

            except Exception as e:
                _logger.error(f"Failed to sync events for issue {issue.bugsink_id}: {e}")


class HavanoErrorEvent(models.Model):
    _name = 'havano.error.event'
    _description = 'System Error Event'
    _order = 'timestamp desc'

    bugsink_id = fields.Char(string='Event ID', required=True, index=True)
    issue_id = fields.Many2one('havano.error.issue', string='Issue', ondelete='cascade')
    timestamp = fields.Datetime(string='Timestamp')
    stacktrace_md = fields.Text(string='Stacktrace')

    # ── Rich tag metadata ────────────────────────────────────────────────────
    site = fields.Char(string='Site')
    user_email = fields.Char(string='User Email')
    app_release = fields.Char(string='Release')
    os_name = fields.Char(string='OS')
    environment = fields.Char(string='Environment')
    error_category = fields.Char(string='Error Category')
    operation = fields.Char(string='Operation')
    current_screen = fields.Char(string='Current Screen')
    event_origin = fields.Char(string='Origin')

    def action_fetch_stacktrace(self):
        """Re-fetches the stacktrace for this event from Bugsink."""
        icp = self.env['ir.config_parameter'].sudo()
        base_url = icp.get_param('havanoposdesk.bugsink_base_url')
        token = icp.get_param('havanoposdesk.bugsink_api_token')
        if not base_url or not token:
            raise UserError("Bugsink API credentials are not configured properly in Settings.")

        base_url = base_url.rstrip('/')
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        }

        for event in self:
            url = f"{base_url}/api/canonical/0/events/{event.bugsink_id}/"
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                full_event = resp.json()

                # Prefer the pre-rendered markdown from the API
                stacktrace_md = full_event.get('stacktrace_md') or ''
                if not stacktrace_md:
                    data_payload = full_event.get('data') or {}
                    exceptions = data_payload.get('exception', {}).get('values', [])
                    lines = []
                    for exc in exceptions:
                        exc_type = exc.get('type', 'Exception')
                        exc_value = exc.get('value', '')
                        lines.append(f"**{exc_type}**: {exc_value}\n\n```")
                        frames = exc.get('stacktrace', {}).get('frames', [])
                        for frame in reversed(frames):
                            fn = frame.get('filename', 'unknown')
                            func = frame.get('function', 'unknown')
                            ln = frame.get('lineno', '?')
                            lines.append(f'  File "{fn}", line {ln}, in {func}')
                        lines.append("```\n")
                    stacktrace_md = '\n'.join(lines) or '*No stacktrace available.*'

                event.write({'stacktrace_md': stacktrace_md})
            except Exception as e:
                _logger.error(f"Failed to fetch stacktrace for event {event.bugsink_id}: {e}")
                raise UserError(f"Failed to fetch stacktrace: {e}")
