# -*- coding: utf-8 -*-
from odoo import models, fields, tools, api, _
from datetime import datetime, timedelta, date
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class HavanoTenantAnalytics(models.Model):
    """
    Read-only analytics report for SaaS tenants.
    Aggregates sales counts, revenue, last sale date, last login, and subscription info
    per tenant using a high-performance PostgreSQL view.
    Also provides get_dashboard_data service for the Tenant Analytics Dashboard.
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

    # ── Dashboard Analytics Service ───────────────────────────────────────────
    @api.model
    def get_dashboard_data(self, tenant_id=False, date_from=False, date_to=False, granularity='weekly'):
        """
        Fetch real, aggregated metrics and timeseries datasets for the
        Tenant Analytics Dashboard across Sales, Purchases, Stock Adjustments,
        and Tenant Activity.
        """
        user = self.env.user
        is_super_admin = user.has_group('base.group_system') or user.id == 1

        # Enforce tenant isolation for non-superadmins
        if not is_super_admin:
            tenant_id = user.tenant_id.id if user.tenant_id else False

        # 1. Fetch available tenants list for dropdown
        tenants_data = []
        if is_super_admin:
            tenants = self.env['havanoposdesk.tenant'].search_read(
                [('active', '=', True)], 
                ['id', 'name'], 
                order='name asc'
            )
            tenants_data = [{'id': t['id'], 'name': t['name']} for t in tenants]
        else:
            if user.tenant_id:
                tenants_data = [{'id': user.tenant_id.id, 'name': user.tenant_id.name}]

        # 2. Date parsing and previous period calculation
        now = fields.Datetime.now()
        today = date.today()

        if not date_from or not date_to:
            # Default to current year (or last 6 months to ensure rich data)
            date_from = f"{today.year}-01-01"
            date_to = today.strftime("%Y-%m-%d")

        try:
            d_start = datetime.strptime(str(date_from)[:10], "%Y-%m-%d").date()
            d_end = datetime.strptime(str(date_to)[:10], "%Y-%m-%d").date()
        except Exception:
            d_start = date(today.year, 1, 1)
            d_end = today
            date_from = d_start.strftime("%Y-%m-%d")
            date_to = d_end.strftime("%Y-%m-%d")

        diff_days = (d_end - d_start).days + 1
        p_start = d_start - timedelta(days=diff_days)
        p_end = d_start - timedelta(days=1)

        start_dt_str = f"{d_start.strftime('%Y-%m-%d')} 00:00:00"
        end_dt_str = f"{d_end.strftime('%Y-%m-%d')} 23:59:59"
        p_start_dt_str = f"{p_start.strftime('%Y-%m-%d')} 00:00:00"
        p_end_dt_str = f"{p_end.strftime('%Y-%m-%d')} 23:59:59"

        # 3. Base SQL Filter Helper
        cr = self.env.cr
        tenant_sql = ""
        tenant_params = []
        if tenant_id:
            if isinstance(tenant_id, list):
                tenant_sql = " AND tenant_id IN %s"
                tenant_params = [tuple(tenant_id)]
            else:
                tenant_sql = " AND tenant_id = %s"
                tenant_params = [int(tenant_id)]

        # 4. Fetch Aggregated Metrics via High-Performance SQL
        # Sales KPIs
        cr.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0)
            FROM havanoposdesk_sale
            WHERE date >= %s AND date <= %s {tenant_sql}
        """, [start_dt_str, end_dt_str] + tenant_params)
        curr_sales_count, curr_sales_total = cr.fetchone() or (0, 0.0)

        cr.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0)
            FROM havanoposdesk_sale
            WHERE date >= %s AND date <= %s {tenant_sql}
        """, [p_start_dt_str, p_end_dt_str] + tenant_params)
        prev_sales_count, prev_sales_total = cr.fetchone() or (0, 0.0)
        sales_growth = self._calculate_growth(curr_sales_total, prev_sales_total)

        # Purchases KPIs
        cr.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0)
            FROM havanoposdesk_purchase
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
        """, [start_dt_str, end_dt_str] + tenant_params)
        curr_purchases_count, curr_purchases_total = cr.fetchone() or (0, 0.0)

        cr.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0)
            FROM havanoposdesk_purchase
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
        """, [p_start_dt_str, p_end_dt_str] + tenant_params)
        prev_purchases_count, prev_purchases_total = cr.fetchone() or (0, 0.0)
        purchases_growth = self._calculate_growth(curr_purchases_total, prev_purchases_total)

        # Stock adjustments KPIs
        cr.execute(f"""
            SELECT 
                COUNT(*),
                COALESCE(SUM(COALESCE(total_amount_difference, 0)), 0),
                COALESCE(SUM(CASE WHEN COALESCE(total_qty_difference, 0) > 0 THEN total_qty_difference ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN COALESCE(total_qty_difference, 0) < 0 THEN ABS(total_qty_difference) ELSE 0 END), 0),
                COUNT(CASE WHEN COALESCE(total_qty_difference, 0) > 0 THEN 1 END),
                COUNT(CASE WHEN COALESCE(total_qty_difference, 0) < 0 THEN 1 END)
            FROM havanoposdesk_stock_adjustment
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
        """, [start_dt_str, end_dt_str] + tenant_params)
        curr_adj_count, curr_adj_valuation, curr_pos_qty, curr_neg_qty, pos_adj_count, neg_adj_count = cr.fetchone() or (0, 0.0, 0.0, 0.0, 0, 0)

        cr.execute(f"""
            SELECT COUNT(*)
            FROM havanoposdesk_stock_adjustment
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
        """, [p_start_dt_str, p_end_dt_str] + tenant_params)
        prev_adj_count = (cr.fetchone() or (0,))[0]

        # Activity stats
        total_activities = curr_sales_count + curr_purchases_count + curr_adj_count
        prev_total_activities = prev_sales_count + prev_purchases_count + prev_adj_count
        activity_growth = self._calculate_growth(total_activities, prev_total_activities)

        kpis = {
            'sales': {
                'total_amount': round(curr_sales_total, 2),
                'transactions_count': curr_sales_count,
                'avg_transaction': round(curr_sales_total / curr_sales_count, 2) if curr_sales_count else 0.0,
                'growth_pct': sales_growth,
            },
            'purchases': {
                'total_amount': round(curr_purchases_total, 2),
                'transactions_count': curr_purchases_count,
                'growth_pct': purchases_growth,
            },
            'stock_adjustments': {
                'operations_count': curr_adj_count,
                'total_valuation_diff': round(curr_adj_valuation, 2),
                'positive_qty': round(curr_pos_qty, 2),
                'negative_qty': round(curr_neg_qty, 2),
            },
            'activity': {
                'total_events': total_activities,
                'sales_events': curr_sales_count,
                'purchase_events': curr_purchases_count,
                'adjustment_events': curr_adj_count,
                'growth_pct': activity_growth,
            }
        }

        # 5. Build Timeline Buckets based on granularity
        buckets = self._generate_timeline_buckets(d_start, d_end, granularity)

        sales_by_bucket = {b['key']: {'amount': 0.0, 'count': 0} for b in buckets}
        purchases_by_bucket = {b['key']: {'amount': 0.0, 'count': 0} for b in buckets}
        adj_by_bucket = {b['key']: {'count': 0, 'pos_qty': 0.0, 'neg_qty': 0.0, 'valuation': 0.0} for b in buckets}

        if granularity == 'daily':
            bucket_expr = "to_char(date, 'YYYY-MM-DD')"
            bucket_expr_p = "to_char(posting_date, 'YYYY-MM-DD')"
        elif granularity == 'monthly':
            bucket_expr = "to_char(date, 'YYYY-MM')"
            bucket_expr_p = "to_char(posting_date, 'YYYY-MM')"
        else:  # 'weekly'
            bucket_expr = "to_char(date, 'IYYY-\"W\"IW')"
            bucket_expr_p = "to_char(posting_date, 'IYYY-\"W\"IW')"

        # Timeline Aggregation: Sales
        cr.execute(f"""
            SELECT 
                {bucket_expr} AS b_key,
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0),
                COUNT(*)
            FROM havanoposdesk_sale
            WHERE date >= %s AND date <= %s {tenant_sql}
            GROUP BY 1
        """, [start_dt_str, end_dt_str] + tenant_params)
        for b_key, b_amount, b_count in cr.fetchall():
            if b_key in sales_by_bucket:
                sales_by_bucket[b_key]['amount'] = float(b_amount or 0.0)
                sales_by_bucket[b_key]['count'] = int(b_count or 0)

        # Timeline Aggregation: Purchases
        cr.execute(f"""
            SELECT 
                {bucket_expr_p} AS b_key,
                COALESCE(SUM(COALESCE(amount_total_base, amount_total, 0)), 0),
                COUNT(*)
            FROM havanoposdesk_purchase
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
            GROUP BY 1
        """, [start_dt_str, end_dt_str] + tenant_params)
        for b_key, b_amount, b_count in cr.fetchall():
            if b_key in purchases_by_bucket:
                purchases_by_bucket[b_key]['amount'] = float(b_amount or 0.0)
                purchases_by_bucket[b_key]['count'] = int(b_count or 0)

        # Timeline Aggregation: Adjustments
        cr.execute(f"""
            SELECT 
                {bucket_expr_p} AS b_key,
                COUNT(*),
                COALESCE(SUM(COALESCE(total_amount_difference, 0)), 0),
                COALESCE(SUM(CASE WHEN COALESCE(total_qty_difference, 0) > 0 THEN total_qty_difference ELSE 0 END), 0),
                COALESCE(SUM(CASE WHEN COALESCE(total_qty_difference, 0) < 0 THEN ABS(total_qty_difference) ELSE 0 END), 0)
            FROM havanoposdesk_stock_adjustment
            WHERE posting_date >= %s AND posting_date <= %s {tenant_sql}
            GROUP BY 1
        """, [start_dt_str, end_dt_str] + tenant_params)
        for b_key, b_count, b_val, b_pos, b_neg in cr.fetchall():
            if b_key in adj_by_bucket:
                adj_by_bucket[b_key]['count'] = int(b_count or 0)
                adj_by_bucket[b_key]['valuation'] = float(b_val or 0.0)
                adj_by_bucket[b_key]['pos_qty'] = float(b_pos or 0.0)
                adj_by_bucket[b_key]['neg_qty'] = float(b_neg or 0.0)

        labels = [b['label'] for b in buckets]

        sales_chart = {
            'labels': labels,
            'amounts': [round(sales_by_bucket[b['key']]['amount'], 2) for b in buckets],
            'counts': [sales_by_bucket[b['key']]['count'] for b in buckets],
        }

        purchase_chart = {
            'labels': labels,
            'amounts': [round(purchases_by_bucket[b['key']]['amount'], 2) for b in buckets],
            'counts': [purchases_by_bucket[b['key']]['count'] for b in buckets],
        }

        stock_chart = {
            'labels': labels,
            'pos_qty': [round(adj_by_bucket[b['key']]['pos_qty'], 2) for b in buckets],
            'neg_qty': [round(adj_by_bucket[b['key']]['neg_qty'], 2) for b in buckets],
            'valuation': [round(adj_by_bucket[b['key']]['valuation'], 2) for b in buckets],
            'operations': [adj_by_bucket[b['key']]['count'] for b in buckets],
        }

        activity_chart = {
            'labels': labels,
            'sales_events': [sales_by_bucket[b['key']]['count'] for b in buckets],
            'purchase_events': [purchases_by_bucket[b['key']]['count'] for b in buckets],
            'adjustment_events': [adj_by_bucket[b['key']]['count'] for b in buckets],
            'total_events': [sales_by_bucket[b['key']]['count'] + purchases_by_bucket[b['key']]['count'] + adj_by_bucket[b['key']]['count'] for b in buckets],
        }

        distribution_chart = {
            'labels': ['Sales Invoices', 'Purchase Orders', 'Stock Adjustments'],
            'data': [curr_sales_count, curr_purchases_count, curr_adj_count],
            'colors': ['#0080ff', '#38bdf8', '#94a3b8'],
        }

        breakdown_chart = {
            'labels': ['Positive Adj (Stock In)', 'Negative Adj (Stock Out)', 'Purchase Orders', 'Sales Invoices'],
            'data': [
                pos_adj_count,
                neg_adj_count,
                curr_purchases_count,
                curr_sales_count,
            ],
            'colors': ['#0080ff', '#38bdf8', '#64748b', '#cbd5e1'],
        }

        return {
            'tenants': tenants_data,
            'selected_tenant_id': int(tenant_id) if tenant_id else False,
            'date_from': date_from,
            'date_to': date_to,
            'granularity': granularity,
            'kpis': kpis,
            'sales_chart': sales_chart,
            'purchase_chart': purchase_chart,
            'stock_chart': stock_chart,
            'activity_chart': activity_chart,
            'distribution_chart': distribution_chart,
            'breakdown_chart': breakdown_chart,
        }

    def _calculate_growth(self, current, previous):
        if not previous or previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100.0, 1)

    def _get_bucket_key(self, dt, granularity):
        if granularity == 'daily':
            return dt.strftime('%Y-%m-%d')
        elif granularity == 'monthly':
            return dt.strftime('%Y-%m')
        else:  # 'weekly'
            year, week, _ = dt.isocalendar()
            return f"{year}-W{week:02d}"

    def _generate_timeline_buckets(self, start_date, end_date, granularity):
        buckets = []
        curr = start_date

        if granularity == 'daily':
            while curr <= end_date:
                key = curr.strftime('%Y-%m-%d')
                label = curr.strftime('%a, %b %d')
                buckets.append({'key': key, 'label': label})
                curr += timedelta(days=1)
        elif granularity == 'monthly':
            # Iterate month by month
            y, m = curr.year, curr.month
            end_y, end_m = end_date.year, end_date.month
            while (y < end_y) or (y == end_y and m <= end_m):
                key = f"{y:04d}-{m:02d}"
                d_obj = date(y, m, 1)
                label = d_obj.strftime('%b %Y')
                buckets.append({'key': key, 'label': label})
                m += 1
                if m > 12:
                    m = 1
                    y += 1
        else:  # 'weekly'
            # Start on Monday of the start_date's week
            curr_monday = curr - timedelta(days=curr.weekday())
            seen_weeks = set()
            while curr_monday <= end_date:
                year, week, _ = curr_monday.isocalendar()
                key = f"{year}-W{week:02d}"
                if key not in seen_weeks:
                    seen_weeks.add(key)
                    label = curr_monday.strftime('%b %d')
                    buckets.append({'key': key, 'label': label})
                curr_monday += timedelta(days=7)

        # Ensure at least 1 bucket exists
        if not buckets:
            buckets.append({'key': 'all', 'label': 'Current Period'})

        return buckets
