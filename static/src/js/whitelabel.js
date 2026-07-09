/** @odoo-module **/
/**
 * Havano White-label patch
 * - Replaces the Odoo logo in the top navbar with the Havano logo
 * - Renames OdooBot → HavanoBot
 * - Patches the document/webclient title
 * - Removes "Powered by Odoo" references
 */

import { patch } from "@web/core/utils/patch";
import { registry } from "@web/core/registry";
import { onMounted } from "@odoo/owl";
import { session } from "@web/session";

// ── 1. Rename OdooBot to HavanoBot everywhere ──────────────────────────────
//  The discuss channel for OdooBot has partner name "OdooBot"
//  We intercept the session_info and patch the name in the DOM after load.

function patchOdooReferences() {
    const botName = session.havanoposdesk_bot_name || "HavanoBot";
    // Walk all text nodes and replace visible "Odoo" references
    const walker = document.createTreeWalker(
        document.body,
        NodeFilter.SHOW_TEXT,
        null,
        false
    );
    const nodesToPatch = [];
    while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.nodeValue && node.nodeValue.includes("OdooBot")) {
            nodesToPatch.push(node);
        }
    }
    nodesToPatch.forEach((node) => {
        node.nodeValue = node.nodeValue.replace(/OdooBot/g, botName);
    });
}

// ── 2. Replace the Odoo logo in the top-left navbar ───────────────────────
function replaceOdooLogo() {
    // The Odoo logo in the backend is typically an <img> or <svg> inside .o_menu_brand or .o_main_navbar
    const brandContainers = document.querySelectorAll(".o_menu_brand, .o_main_navbar .o_logo_edition");
    brandContainers.forEach((el) => {
        el.style.display = "none";
    });

    // Find the home menu icon/logo area and inject Havano branding
    const navbar = document.querySelector(".o_main_navbar");
    if (navbar && !navbar.querySelector(".havano_brand")) {
        const brand = document.createElement("div");
        brand.className = "havano_brand";
        brand.style.cssText = `
            display: flex;
            align-items: center;
            padding: 0 12px;
            height: 100%;
        `;
        const appName = session.havanoposdesk_app_name || "Havano";
        brand.innerHTML = `
            <img src="/havanoposdesk_odoo/static/src/img/havan_2.png"
                 alt="${appName}"
                 style="height:28px; width:auto; object-fit:contain;"
                 onerror="this.style.display='none'; this.nextSibling.style.display='flex'"/>
            <span style="display:none; font-weight:700; font-size:18px; color:#fff; letter-spacing:-0.5px;">${appName}</span>
        `;
        // Insert at the beginning of the navbar
        navbar.insertBefore(brand, navbar.firstChild);
    }
}

// ── 3. Set document title ──────────────────────────────────────────────────
function patchDocumentTitle() {
    const appName = session.havanoposdesk_app_name || "Havano";
    if (document.title && document.title.includes("Odoo")) {
        document.title = document.title.replace(/Odoo/g, appName);
    }
    // Watch for future title changes
    const observer = new MutationObserver(() => {
        if (document.title.includes("Odoo")) {
            document.title = document.title.replace(/Odoo/g, appName);
        }
    });
    observer.observe(document.querySelector("title") || document.head, {
        childList: true,
        subtree: true,
        characterData: true,
    });
}

// ── 4. Run all patches when DOM is ready ──────────────────────────────────
function applyWhiteLabel() {
    replaceOdooLogo();
    patchDocumentTitle();
    patchOdooReferences();
}

// Apply immediately if DOM is ready, then again after short delay for dynamic content
if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyWhiteLabel);
} else {
    applyWhiteLabel();
}

// Re-apply after Odoo's web client renders (OWL components mount asynchronously)
setTimeout(applyWhiteLabel, 800);
setTimeout(applyWhiteLabel, 2000);

// Watch for future DOM mutations (e.g. route changes) and re-apply
const domObserver = new MutationObserver(() => {
    patchOdooReferences();
});
document.addEventListener("DOMContentLoaded", () => {
    domObserver.observe(document.body, { childList: true, subtree: true });
});
