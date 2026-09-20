// Copyright (c) 2026, Hex Flow and contributors
// For license information, please see license.txt

frappe.ui.form.on("Medication Administration Log", {
	setup(frm) {
		frm.set_query("participant", () => ({
			query:
				"care_management.care_management.doctype.medication_administration_log.medication_administration_log.search_medication_log_participants",
		}));
	},
	refresh(frm) {
		if (frm.is_new() || !frm.doc.participant) {
			return;
		}
		frappe
			.call({
				method: "care_management.care_management.audit_export.can_download_medication_audit_bundle",
				args: {
					participant: frm.doc.participant,
				},
			})
			.then((response) => {
				if (!response.message) {
					return;
				}
				frm.add_custom_button(__("Medication Audit Bundle"), () => {
					const params = new URLSearchParams({
						participant: frm.doc.participant,
					});
					window.location.assign(
						`/api/method/care_management.care_management.audit_export.download_medication_audit_bundle?${params.toString()}`
					);
				});
			});
	},
});
