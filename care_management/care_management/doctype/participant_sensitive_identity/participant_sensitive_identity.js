frappe.ui.form.on("Participant Sensitive Identity", {
	refresh(frm) {
		frm.set_df_property("participant", "read_only", !frm.is_new());
	},
});
