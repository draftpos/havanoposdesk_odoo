from odoo import models, fields, tools, api, _
import logging

_logger = logging.getLogger(__name__)


class HavanoTenantAnalytics(models.Model):
    """
    Read-only analytics report for SaaS tenants.
    Aggregates sales counts, revenue, last sale date, last login, and subscription info
    per tenant using a high-performance PostgreSQL view.
    """
    _name = 'havanoposdesk.tenant.analytics'
    _description = 'Tenant Analytics Report'
    _auto = False
    _rec_name = 'tenant_name'
    _order = 'total_sales_count desc, total_sales_amount desc, tenant_name asc'

    # ── Identity ──────────────────────────────────────────────────────────────
    tenant_id = fields.Many2one('havanoposdesk.tenant', string='Tenant', readonly=True)
    tenant_name = fields.Char(string='Tenant Name', readonly=True)

    # ── Subscription ──────────────────────────────────────────────────────────
    subscription_plan_id = fields.Many2one('havanoposdesk.subscription.plan', string='Subscription Plan', readonly=True)
    plan_name = fields.Char(string='Plan Name', readonly=True)
    subscription_state = fields.Selection([
        ('active', 'Active'),
        ('pending', 'Pending Payment'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Subscription Status', readonly=True)
    is_trial = fields.Boolean(string='Demo / Trial', readonly=True)
    subscription_end_date = fields.Date(string='Expiry Date', readonly=True)

    # ── Sales KPIs ────────────────────────────────────────────────────────────
    total_sales_count = fields.Integer(string='# Sales', readonly=True)
    total_sales_amount = fields.Float(string='Total Revenue ($)', readonly=True, digits=(16, 2))
    last_sale_date = fields.Date(string='Last Sale Date', readonly=True)

    # ── Users & Activity ──────────────────────────────────────────────────────
    user_count = fields.Integer(string='# Users', readonly=True)
    last_login = fields.Datetime(string='Recent Login', readonly=True)
    last_activity = fields.Datetime(string='Recent Usage', readonly=True)

    # ── Wallet & Currency ─────────────────────────────────────────────────────
    account_balance = fields.Float(string='Wallet Balance ($)', readonly=True, digits=(16, 2))
    currency_id = fields.Many2one('res.currency', string='Currency', compute='_compute_default_currency', readonly=True)

    def _compute_default_currency(self):
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        default_cur_id = usd.id if usd else self.env.company.currency_id.id
        for record in self:
            record.currency_id = default_cur_id

    # ─────────────────────────────────────────────────────────────────────────
    def init(self):
        """Create or replace the underlying PostgreSQL view."""
        tools.drop_view_if_exists(self.env.cr, 'havanoposdesk_tenant_analytics')
        self.env.cr.execute("""
            CREATE OR REPLACE VIEW havanoposdesk_tenant_analytics AS (
                SELECT
                    t.id                                        AS id,
                    t.id                                        AS tenant_id,
                    t.name                                      AS tenant_name,
                    t.subscription_plan_id                      AS subscription_plan_id,
                    COALESCE(sp.name, 'No Plan')                AS plan_name,
                    COALESCE(t.subscription_state, 'active')   AS subscription_state,
                    CASE
                        WHEN t.subscription_plan_id IS NULL THEN TRUE
                        WHEN sp.is_trial = TRUE OR COALESCE(sp.price, 0) = 0 OR LOWER(sp.name) LIKE '%demo%' OR LOWER(sp.name) LIKE '%trial%' THEN TRUE
                        WHEN t.is_trial = TRUE THEN TRUE
                        ELSE FALSE
                    END                                         AS is_trial,
                    t.subscription_end_date                     AS subscription_end_date,
                    COALESCE(t.account_balance, 0)              AS account_balance,

                    -- Sales KPIs: includes all sales where not return or quotation, handles NULLs safely
                    COALESCE(s.total_sales_count, 0)            AS total_sales_count,
                    COALESCE(s.total_sales_amount, 0.0)         AS total_sales_amount,
                    s.last_sale_date                            AS last_sale_date,

                    -- Users & Logins
                    COALESCE(u.user_count, 0)                   AS user_count,
                    u.last_login                                AS last_login,

                    -- Recent Usage: most recent of user login or sales creation
                    CASE
                        WHEN u.last_login IS NOT NULL AND s.last_sale_create_date IS NOT NULL
                            THEN GREATEST(u.last_login, s.last_sale_create_date)
                        ELSE COALESCE(u.last_login, s.last_sale_create_date)
                    END                                         AS last_activity

                FROM havanoposdesk_tenant t
                LEFT JOIN havanoposdesk_subscription_plan sp
                    ON sp.id = t.subscription_plan_id

                -- Aggregate sales per tenant
                LEFT JOIN (
                    SELECT
                        tenant_id,
                        COUNT(*)                                            AS total_sales_count,
                        SUM(COALESCE(amount_total_base, amount_total, 0.0)) AS total_sales_amount,
                        MAX(posting_date)                                   AS last_sale_date,
                        MAX(create_date)                                    AS last_sale_create_date
                    FROM havanoposdesk_sale
                    WHERE COALESCE(is_return, FALSE) = FALSE
                      AND COALESCE(is_quotation, FALSE) = FALSE
                      AND COALESCE(state, 'done') != 'cancelled'
                    GROUP BY tenant_id
                ) s ON s.tenant_id = t.id

                -- Aggregate user count and last login from res_users_log
                LEFT JOIN (
                    SELECT
                        u.tenant_id,
                        COUNT(DISTINCT u.id)    AS user_count,
                        MAX(l.create_date)      AS last_login
                    FROM res_users u
                    LEFT JOIN res_users_log l ON l.create_uid = u.id
                    WHERE u.active = TRUE
                      AND u.tenant_id IS NOT NULL
                    GROUP BY u.tenant_id
                ) u ON u.tenant_id = t.id

                WHERE t.active = TRUE
            )
        """)

    # ── Action Methods ────────────────────────────────────────────────────────
    def action_open_tenant(self):
        """Open the tenant form from the analytics list row."""
        self.ensure_one()
        return {
            'name': _('Tenant: %s', self.tenant_name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.tenant',
            'res_id': self.tenant_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_sales(self):
        """Drill down into this tenant's sales records."""
        self.ensure_one()
        return {
            'name': _('%s – Sales Invoices', self.tenant_name),
            'type': 'ir.actions.act_window',
            'res_model': 'havanoposdesk.sale',
            'view_mode': 'list,form',
            'domain': [
                ('tenant_id', '=', self.tenant_id.id),
                ('is_return', '=', False),
                ('is_quotation', '=', False),
            ],
            'context': {
                'default_tenant_id': self.tenant_id.id,
                'search_default_tenant_id': self.tenant_id.id,
            },
            'target': 'current',
        }
