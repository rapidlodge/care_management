"""
One-off seed script for Participant Profile master/lookup data.
Run with:  bench execute care_management.seed_master_data.run
(place this file at care_management/care_management/seed_master_data.py in your app,
or run the contents directly inside `bench console`)
"""

import frappe


def run():
	seed("Living Arrangement", "arrangement_name", [
		"Dependent children", "Grandparents", "Lives alone", "Other Relatives",
	])

	seed("Consent Type", "consent_name", [
		"Consent to Administer Medication", "Exchange of Information",
		"Filming and Photography", "Participant Consent Form",
	])

	seed("Secondary Disability Type", "disability_name", [
		"Acquired Brain Injury", "Addiction", "Anxiety", "Autism",
		# NOTE: screenshot crop cuts off here — add any remaining
		# checkbox values from the full iPlanit list once visible.
	])

	seed("Restrictive Practice Type", "practice_name", [
		"Seclusion", "Chemical restraint", "Mechanical restraint", "Physical restraint",
	])

	frappe.db.commit()


def seed(doctype, fieldname, values):
	for v in values:
		if not frappe.db.exists(doctype, v):
			frappe.get_doc({"doctype": doctype, fieldname: v}).insert(ignore_permissions=True)
