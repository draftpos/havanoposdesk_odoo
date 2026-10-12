/** @odoo-module **/

import { Component, useEffect } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { CharField } from "@web/views/fields/char/char_field";
import { ListTextField, TextField } from "@web/views/fields/text/text_field";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { X2ManyField, x2ManyField } from "@web/views/fields/x2many/x2many_field";
import { ListRenderer } from "@web/views/list/list_renderer";

export class SectionAndNoteListRenderer extends ListRenderer {
    setup() {
        super.setup();
        this.titleField = "name";
        useEffect(
            (editedRecord) => this.focusToName(editedRecord),
            () => [this.props.list.editedRecord]
        );
    }

    isSectionOrNote(record) {
        return Boolean(record && record.data && record.data.display_type);
    }

    focusToName(editRec) {
        if (editRec && editRec.isNew && this.isSectionOrNote(editRec)) {
            const col = this.columns.find((c) => c.name === this.titleField);
            if (col) {
                this.focusCell(col, null);
            }
        }
    }

    getColumns(record) {
        const columns = super.getColumns(record);
        if (this.isSectionOrNote(record)) {
            const sectionCols = columns.filter(
                (col) => col.widget === "handle" || col.name === this.titleField
            );
            return sectionCols.map((col) => {
                if (col.name === this.titleField) {
                    return { ...col, colspan: Math.max(1, columns.length - sectionCols.length + 1) };
                }
                return { ...col };
            });
        }
        return columns;
    }

    getRowClass(record) {
        const existingClasses = super.getRowClass(record);
        if (record && record.data && record.data.display_type) {
            return `${existingClasses} o_is_${record.data.display_type}`;
        }
        return existingClasses;
    }
}

export class SectionAndNoteText extends Component {
    static template = "havanoposdesk_odoo.SectionAndNoteText";
    static props = { ...standardFieldProps };

    get componentToUse() {
        return this.props.record.data.display_type === "line_section" ? CharField : TextField;
    }
}

export class ListSectionAndNoteText extends SectionAndNoteText {
    get componentToUse() {
        return this.props.record.data.display_type !== "line_section"
            ? ListTextField
            : super.componentToUse;
    }
}

export class SectionAndNoteFieldOne2Many extends X2ManyField {
    static components = {
        ...super.components,
        ListRenderer: SectionAndNoteListRenderer,
    };
}

export const sectionAndNoteFieldOne2Many = {
    ...x2ManyField,
    component: SectionAndNoteFieldOne2Many,
    additionalClasses: [...(x2ManyField.additionalClasses || []), "o_field_one2many"],
};

export const sectionAndNoteText = {
    component: SectionAndNoteText,
    additionalClasses: ["o_field_text"],
};

export const listSectionAndNoteText = {
    ...sectionAndNoteText,
    component: ListSectionAndNoteText,
};

registry.category("fields").add("section_and_note_one2many", sectionAndNoteFieldOne2Many);
registry.category("fields").add("section_and_note_text", sectionAndNoteText);
registry.category("fields").add("list.section_and_note_text", listSectionAndNoteText);
