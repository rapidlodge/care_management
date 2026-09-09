frappe.ui.form.on("Controlled Medication Transaction", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query: "care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction.search_controlled_transaction_participants",
		}));
		frm.set_query("medication_plan", () => ({
			query: "care_management.care_management.doctype.controlled_medication_transaction.controlled_medication_transaction.search_controlled_transaction_plans",
		}));
	},
	refresh(frm) {
		set_controlled_transaction_preview(frm);
	},
	transaction_type(frm) {
		set_controlled_transaction_preview(frm);
	},
	quantity(frm) {
		set_controlled_transaction_preview(frm);
	},
});

function set_controlled_transaction_preview(frm) {
	if (!frm.is_new()) {
		return;
	}
	if (!frm.doc.transaction_type) {
		return;
	}
	const source_generated = ["Administration", "Disposal", "Return to Pharmacy"].includes(frm.doc.transaction_type);
	if (source_generated) {
		return;
	}
	const quantity = flt(frm.doc.quantity || 0);
	const direction = ["Opening Balance", "Receipt", "Correction Increase"].includes(frm.doc.transaction_type)
		? "Increase"
		: "Decrease";
	const before = flt(frm.doc.balance_before || 0);
	const after = direction === "Increase" ? before + quantity : before - quantity;
	frm.set_value("direction", direction);
	frm.set_value("balance_before", before);
	frm.set_value("balance_after", after);
	frm.set_value("actor", frappe.session.user);
	frm.set_value("source_doctype", "Controlled Medication Transaction");
	frm.set_value("source_docname", frm.doc.name || "pending");
	frm.set_value("source_action", frm.doc.transaction_type);
	frm.set_value("source_key", "client-preview");
}
