/** @odoo-module **/

import { registry } from "@web/core/registry";

console.log("🔔 HAVANO: price_approval_notification.js loaded");

const seenRequestIds = new Set();
let containerEl = null;

function getOrCreateContainer() {
    if (!containerEl || !document.body.contains(containerEl)) {
        containerEl = document.createElement("div");
        containerEl.className = "havano-price-approval-container";
        document.body.appendChild(containerEl);
    }
    return containerEl;
}

function playNotificationChime() {
    try {
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        if (!AudioContext) return;
        const ctx = new AudioContext();
        const now = ctx.currentTime;

        // Tone 1
        const osc1 = ctx.createOscillator();
        const gain1 = ctx.createGain();
        osc1.type = "sine";
        osc1.frequency.setValueAtTime(587.33, now); // D5
        gain1.gain.setValueAtTime(0.12, now);
        gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
        osc1.connect(gain1);
        gain1.connect(ctx.destination);
        osc1.start(now);
        osc1.stop(now + 0.25);

        // Tone 2
        const osc2 = ctx.createOscillator();
        const gain2 = ctx.createGain();
        osc2.type = "sine";
        osc2.frequency.setValueAtTime(880.00, now + 0.1); // A5
        gain2.gain.setValueAtTime(0.18, now + 0.1);
        gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.4);
        osc2.connect(gain2);
        gain2.connect(ctx.destination);
        osc2.start(now + 0.1);
        osc2.stop(now + 0.4);
    } catch (e) {
        // Audio playback failure or autoplay restriction - safely ignore
    }
}

function showApprovalToast(req, env) {
    if (!req || !req.request_id) return;
    if (seenRequestIds.has(req.request_id)) return;
    seenRequestIds.add(req.request_id);

    playNotificationChime();

    const container = getOrCreateContainer();
    const toast = document.createElement("div");
    toast.className = "havano-price-approval-toast";
    toast.dataset.requestId = req.request_id;

    const cashierInfo = req.cashier_name || req.cashier || "Cashier";
    const terminalInfo = req.pos_profile || req.terminal_id || "POS";
    const prodName = req.product_name || "Custom Item";
    const qty = req.quantity || 1.0;
    const origPrice = Number(req.original_price || 0).toFixed(2);
    const reqPrice = Number(req.requested_price || 0).toFixed(2);
    const diffPercent = req.difference_percent !== undefined ? req.difference_percent : (
        req.original_price ? (((req.requested_price - req.original_price) / req.original_price) * 100).toFixed(1) : 0
    );
    const diffSign = diffPercent > 0 ? `+${diffPercent}%` : `${diffPercent}%`;
    const reasonText = req.note || req.reason || "";

    toast.innerHTML = `
        <div class="havano-toast-header">
            <div class="havano-toast-title-box">
                <div class="havano-toast-icon">🔔</div>
                <div>
                    <h4 class="havano-toast-title">Price Change Request</h4>
                    <div class="havano-toast-meta">
                        <span class="havano-toast-badge">${cashierInfo}</span>
                        <span>·</span>
                        <span>${terminalInfo}</span>
                    </div>
                </div>
            </div>
            <button class="havano-toast-close" title="Dismiss">✕</button>
        </div>
        <div class="havano-toast-body">
            <div class="havano-toast-product">
                <span>${prodName}</span>
                <span style="color: #6b7280; font-weight: normal;">Qty: ${qty}</span>
            </div>
            <div class="havano-toast-price-row">
                <div class="havano-price-compare">
                    <span class="havano-price-orig">$${origPrice}</span>
                    <span class="havano-price-arrow">→</span>
                    <span class="havano-price-req">$${reqPrice}</span>
                </div>
                <span class="havano-discount-tag">${diffSign}</span>
            </div>
            ${reasonText ? `<div class="havano-toast-reason">"${reasonText}"</div>` : ""}
        </div>
        <div class="havano-toast-actions">
            <button class="havano-toast-btn havano-toast-btn-approve" id="btn-approve">
                ✓ Approve $${reqPrice}
            </button>
            <button class="havano-toast-btn havano-toast-btn-review" id="btn-review">
                Review / Counter
            </button>
        </div>
    `;

    // Close button
    toast.querySelector(".havano-toast-close").addEventListener("click", () => {
        toast.classList.remove("visible");
        setTimeout(() => toast.remove(), 400);
    });

    // Quick Approve button
    const approveBtn = toast.querySelector("#btn-approve");
    approveBtn.addEventListener("click", async () => {
        approveBtn.disabled = true;
        approveBtn.textContent = "Approving...";
        try {
            const resp = await fetch(`/api/pos/price-approval/resolve/${req.request_id}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action: "approve", note: "Approved via quick notification" })
            });
            const res = await resp.json();
            const isOk = res && (
                res.status === "success" || 
                res.success === true || 
                res.status === "approved" || 
                res.approval_status === "approved" || 
                (res.data && (res.data.status === "approved" || res.data.approval_status === "approved"))
            );
            if (isOk) {
                toast.style.borderLeftColor = "#10b981";
                toast.querySelector(".havano-toast-body").innerHTML = `
                    <div style="color: #059669; font-weight: 700; display: flex; align-items: center; gap: 6px;">
                        ✓ Price approved at $${reqPrice}
                    </div>
                `;
                toast.querySelector(".havano-toast-actions")?.remove();
                setTimeout(() => {
                    toast.classList.remove("visible");
                    setTimeout(() => toast.remove(), 400);
                }, 2000);
            } else {
                const errMsg = res.message || (res.data && res.data.message) || "Unable to approve request";
                alert("Could not approve: " + errMsg);
                approveBtn.disabled = false;
                approveBtn.textContent = `✓ Approve $${reqPrice}`;
            }
        } catch (e) {
            console.error("Error approving price request:", e);
            approveBtn.disabled = false;
            approveBtn.textContent = `✓ Approve $${reqPrice}`;
        }
    });

    // Review / Counter button (Opens Action or Form)
    toast.querySelector("#btn-review").addEventListener("click", () => {
        toast.classList.remove("visible");
        setTimeout(() => toast.remove(), 400);
        if (env && env.services && env.services.action) {
            env.services.action.doAction({
                name: "Price Approvals",
                type: "ir.actions.act_window",
                res_model: "pos.price.approval.request",
                views: [[false, "list"], [false, "form"]],
                context: { search_default_filter_pending: 1 },
                target: "current"
            });
        }
    });

    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add("visible"));
}

export const priceApprovalNotificationService = {
    dependencies: ["bus_service", "action", "notification"],
    start(env, { bus_service }) {
        // 1. Bus listener (Instant WebSocket Push)
        if (bus_service) {
            try {
                bus_service.subscribe("new_price_approval_request", (payload) => {
                    showApprovalToast(payload, env);
                });
                bus_service.subscribe("pos:new_price_approval_request", (payload) => {
                    showApprovalToast(payload, env);
                });
            } catch (err) {
                console.warn("Could not subscribe to bus_service for price approvals:", err);
            }
        }

        // 2. Periodic Polling Watchdog (every 6 seconds fallback)
        async function checkPendingRequests() {
            try {
                const resp = await fetch("/api/pos/price-approval/pending");
                if (resp.ok) {
                    const json = await resp.json();
                    if (json && json.status === "success" && Array.isArray(json.data)) {
                        for (const req of json.data) {
                            showApprovalToast(req, env);
                        }
                    }
                }
            } catch (e) {
                // Network issue or offline - ignore
            }
        }

        // Initial check and recurring interval
        setTimeout(checkPendingRequests, 3000);
        setInterval(checkPendingRequests, 6000);
    }
};

registry.category("services").add("price_approval_notification", priceApprovalNotificationService);
