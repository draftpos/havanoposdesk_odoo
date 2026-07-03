/** @odoo-module **/

import { Component, useState, onWillStart } from "@odoo/owl";

export class PwaPrompt extends Component {
    setup() {
        this.state = useState({
            showPrompt: false,
            isIosSafari: false,
        });

        this.deferredPrompt = null;

        onWillStart(async () => {
            // Check if running in standalone
            const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone;
            const dismissed = localStorage.getItem('pwa_prompt_dismissed');

            if (isStandalone || dismissed) {
                return;
            }

            // Detect iOS Safari
            const ua = window.navigator.userAgent;
            const webkit = !!ua.match(/WebKit/i);
            const isIos = !!ua.match(/iPad/i) || !!ua.match(/iPhone/i);
            this.state.isIosSafari = isIos && webkit && !ua.match(/CriOS/i) && !ua.match(/OPiOS/i) && !ua.match(/FxiOS/i);

            if (this.state.isIosSafari) {
                // For iOS Safari, we just show the prompt immediately (if not dismissed)
                this.state.showPrompt = true;
            } else {
                // For Chrome/Android, wait for beforeinstallprompt event.
                // mobile_kanban_design.js captures this globally and stores it in window.deferredPwaPrompt
                if (window.deferredPwaPrompt) {
                    this.deferredPrompt = window.deferredPwaPrompt;
                    this.state.showPrompt = true;
                } else {
                    // It might fire a bit later
                    window.addEventListener('beforeinstallprompt', (e) => {
                        this.deferredPrompt = e;
                        this.state.showPrompt = true;
                    });
                }
            }
        });
    }

    dismiss() {
        localStorage.setItem('pwa_prompt_dismissed', 'true');
        this.state.showPrompt = false;
    }

    async installApp() {
        if (this.deferredPrompt) {
            // Show the install prompt
            this.deferredPrompt.prompt();
            // Wait for the user to respond to the prompt
            const { outcome } = await this.deferredPrompt.userChoice;
            // We've used the prompt, and can't use it again, throw it away
            this.deferredPrompt = null;
            if (outcome === 'accepted') {
                this.state.showPrompt = false;
            }
        }
    }
}

PwaPrompt.template = "havanoposdesk.PwaPrompt";
