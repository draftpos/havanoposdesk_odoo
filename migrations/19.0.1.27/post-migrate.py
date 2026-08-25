"""Clear stale browser-invalid domains from Account actions."""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    for xml_id in (
        'havanoposdesk_odoo.action_havanoposdesk_account',
        'havanoposdesk_odoo.action_havanoposdesk_cash_balance_report',
    ):
        action = env.ref(xml_id, raise_if_not_found=False)
        if action:
            action.write({'domain': '[]'})
