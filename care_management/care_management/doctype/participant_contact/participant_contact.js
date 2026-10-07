frappe.ui.form.on("Participant Contact", {
	refresh(frm) {
		frm.set_df_property("participant", "read_only", !frm.is_new());
	},
});
