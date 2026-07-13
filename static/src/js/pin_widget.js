/** @odoo-module **/

import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { Component, useRef, useState, onWillUpdateProps } from "@odoo/owl";

export class PosPinBoxes extends Component {
    setup() {
        this.inputRefs = [useRef("input0"), useRef("input1"), useRef("input2"), useRef("input3")];
        
        // Initialize the state based on the current record value
        const val = this.props.record.data[this.props.name] || "";
        this.state = useState({
            chars: [
                val[0] || "",
                val[1] || "",
                val[2] || "",
                val[3] || ""
            ]
        });

        onWillUpdateProps((nextProps) => {
            const newVal = nextProps.record.data[this.props.name] || "";
            this.state.chars = [
                newVal[0] || "",
                newVal[1] || "",
                newVal[2] || "",
                newVal[3] || ""
            ];
        });
    }

    get isReadonly() {
        return this.props.readonly;
    }

    onInput(index, ev) {
        let val = ev.target.value;
        // Keep only the last character if they pasted or typed multiple
        if (val.length > 1) {
            val = val.slice(-1);
        }
        
        // Only allow digits
        if (!/^\d*$/.test(val)) {
            ev.target.value = this.state.chars[index];
            return;
        }

        this.state.chars[index] = val;

        // Auto-focus next
        if (val !== "" && index < 3) {
            this.inputRefs[index + 1].el.focus();
        }

        this._updateRecord();
    }

    onKeyDown(index, ev) {
        if (ev.key === "Backspace" && this.state.chars[index] === "" && index > 0) {
            this.inputRefs[index - 1].el.focus();
            // Optional: clear previous box on backspace
            // this.state.chars[index - 1] = "";
            // this._updateRecord();
        }
    }

    _updateRecord() {
        const fullPin = this.state.chars.join("");
        this.props.record.update({ [this.props.name]: fullPin });
    }
}

PosPinBoxes.template = "havanoposdesk_odoo.PosPinBoxes";
PosPinBoxes.components = {};
PosPinBoxes.props = {
    ...CharField.props,
};
PosPinBoxes.supportedTypes = ["char"];

registry.category("fields").add("pos_pin_boxes", {
    component: PosPinBoxes,
    supportedTypes: ["char"],
    extractProps: CharField.extractProps,
});
