/** @odoo-module **/

import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

/**
 * Subscription Expiry Banner
 * 
 * A dismissible banner that appears when the tenant's subscription 
 * is expiring soon (≤ warning_days) or has expired.
 * 
 * Dismissal is stored in sessionStorage so it reappears on next login session.
 */
export class SubscriptionBanner extends Component {
    static template = "havanoposdesk_odoo.SubscriptionBanner";

    setup() {
        this.orm = useService("orm");

        this.state = useState({
            show: false,
            dismissed: false,
            days_left: null,
            state: "",
            plan_name: "",
            end_date: "",
            is_expiring_soon: false,
            is_expired: false,
            warning_days: 3,
        });

        onWillStart(async () => {
            if (sessionStorage.getItem("havano_sub_banner_dismissed") === "1") {
                this.state.dismissed = true;
                return;
            }
            await this.fetchSubscriptionInfo();
        });
    }

    async fetchSubscriptionInfo() {
        try {
            const info = await this.orm.call(
                "havanoposdesk.tenant",
                "get_subscription_info",
                []
            );

            if (info && info.show_banner) {
                this.state.show = true;
                this.state.days_left = info.days_left;
                this.state.state = info.state;
                this.state.plan_name = info.plan_name || "";
                this.state.end_date = info.end_date || "";
                this.state.is_expiring_soon = info.is_expiring_soon;
                this.state.is_expired = info.is_expired;
                this.state.warning_days = info.warning_days || 3;
            }
        } catch (e) {
            console.warn("SubscriptionBanner: Could not fetch subscription info", e);
        }
    }

    get bannerClass() {
        if (this.state.is_expired) {
            return "havano-sub-banner--danger";
        }
        if (this.state.is_expiring_soon && this.state.days_left !== null && this.state.days_left <= 0) {
            return "havano-sub-banner--danger";
        }
        return "havano-sub-banner--warning";
    }

    get bannerIcon() {
        return this.state.is_expired ? "fa-exclamation-circle" : "fa-exclamation-triangle";
    }

    get bannerMessage() {
        const days = this.state.days_left;

        if (this.state.state === "cancelled") {
            return "Your subscription has been cancelled. Please renew to continue using all features.";
        }

        if (this.state.is_expired || (days !== null && days < 0)) {
            return "Your subscription has expired! Please renew immediately to avoid service interruption.";
        }

        if (days === 0) {
            return "Your subscription expires today! Renew now to avoid losing access.";
        }

        if (days === 1) {
            return "Your subscription expires tomorrow! Renew now to avoid service interruption.";
        }

        if (days !== null && days <= this.state.warning_days) {
            return `Your subscription expires in ${days} day(s)! Renew now to avoid service interruption.`;
        }

        return `Your subscription expires in ${days} day(s).`;
    }

    get isVisible() {
        return this.state.show && !this.state.dismissed;
    }

    dismiss() {
        this.state.dismissed = true;
        sessionStorage.setItem("havano_sub_banner_dismissed", "1");
    }
}

registry.category("systray").add("havanoposdesk_odoo.SubscriptionBanner", {
    Component: SubscriptionBanner,
}, { sequence: 0 });
