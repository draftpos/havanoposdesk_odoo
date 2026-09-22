/** @odoo-module **/
/**
 * Havano White-label patch (Optimized for Ultra-Fast Rendering)
 * - Replaces the Odoo logo in the top navbar with the Havano logo
 * - Renames OdooBot in channels
 * - Patches document/webclient title
 * - Removes heavy MutationObservers and layout-thrashing TreeWalkers
 */

import { session } from "@web/session";

// ── 0. Patch localStorage to prevent Menu Quota errors ────────────────────────
const originalSetItem = Storage.prototype.setItem;
Storage.prototype.setItem = function(key, value) {
    try {
        originalSetItem.apply(this, arguments);
    } catch (e) {
        if (e.name === 'QuotaExceededError' || (e.message && e.message.includes('quota'))) {
            if (key === 'menus' || (typeof key === 'string' && key.includes('menus'))) {
                return;
            }
        }
        throw e;
    }
};

// ── 1. Target OdooBot in Discuss channels without walking entire DOM ───────────
function patchOdooBotTargeted() {
    const botName = session.havanoposdesk_bot_name || "HavanoBot";
    const discussNodes = document.querySelectorAll(
        ".o_channel_name, .o-mail-Discuss-sidebar, .o-mail-Chatter, .o_mail_notification"
    );
    discussNodes.forEach((node) => {
        if (node.textContent && node.textContent.includes("OdooBot")) {
            node.innerHTML = node.innerHTML.replace(/OdooBot/g, botName);
        }
    });
}

// ── 2. Inject Havano Logo & Branding in the Top Navbar ─────────────────────────
function replaceOdooLogo() {
    const navbar = document.querySelector(".o_main_navbar");
    if (navbar && !navbar.querySelector(".havano_brand")) {
        const brand = document.createElement("div");
        brand.className = "havano_brand";
        brand.style.cssText = "display:flex; align-items:center; padding:0 12px; height:100%;";
        const appName = session.havanoposdesk_app_name || "Havano";
        brand.innerHTML = `
            <img src="/havanoposdesk_odoo/static/src/img/havan_2.png"
                 alt="${appName}"
                 style="height:28px; width:auto; object-fit:contain;"
                 onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'"/>
            <span style="display:none; font-weight:700; font-size:18px; color:#fff; letter-spacing:-0.5px;">${appName}</span>
        `;
        navbar.insertBefore(brand, navbar.firstChild);
    }
}

function addLogoutLink() {
    const navbar = document.querySelector(".o_main_navbar");
    if (navbar && !navbar.querySelector(".havano_logout_link")) {
        const logoutLink = document.createElement("a");
        logoutLink.className = "havano_logout_link";
        logoutLink.href = "/web/session/logout";
        logoutLink.textContent = "Logout";
        logoutLink.setAttribute("aria-label", "Logout");
        const systray = navbar.querySelector(".o_menu_systray");
        if (systray) {
            systray.appendChild(logoutLink);
        } else {
            navbar.appendChild(logoutLink);
        }
    }
}

// ── 3. Set Document Title (observe only <title> element) ───────────────────────
function patchDocumentTitle() {
    const appName = session.havanoposdesk_app_name || "Havano";
    if (document.title && document.title.includes("Odoo")) {
        document.title = document.title.replace(/Odoo/g, appName);
    }
    const titleEl = document.querySelector("title");
    if (titleEl) {
        const observer = new MutationObserver(() => {
            if (document.title.includes("Odoo")) {
                document.title = document.title.replace(/Odoo/g, appName);
            }
        });
        observer.observe(titleEl, { childList: true, characterData: true });
    }
}

// ── 4. Apply White-label when DOM is ready ────────────────────────────────────
function applyWhiteLabel() {
    replaceOdooLogo();
    addLogoutLink();
    patchDocumentTitle();
    patchOdooBotTargeted();
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyWhiteLabel);
} else {
    applyWhiteLabel();
}

// Re-apply once after Owl components mount
setTimeout(applyWhiteLabel, 600);
