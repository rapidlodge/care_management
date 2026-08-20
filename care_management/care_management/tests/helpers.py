import frappe
from frappe.utils import today


TEST_PARTICIPANT_NAME = "R1 Test Participant"


def _ensure_named_master(doctype, fieldname, value):
	if not frappe.db.exists(doctype, value):
		frappe.get_doc(
			{
				"doctype": doctype,
				fieldname: value,
			}
		).insert(ignore_permissions=True)
	return value


def ensure_test_participant():
	existing = frappe.db.get_value(
		"Participant Profile",
		{"participant": TEST_PARTICIPANT_NAME},
		"name",
	)

	if existing:
		return existing

	living_arrangement = _ensure_named_master(
		"Living Arrangement",
		"arrangement_name",
		"R1 Test Living Arrangement",
	)
	consent_type = _ensure_named_master(
		"Consent Type",
		"consent_name",
		"R1 Test Consent",
	)
	secondary_disability = _ensure_named_master(
		"Secondary Disability Type",
		"disability_name",
		"R1 Test Secondary Disability",
	)

	doc = frappe.get_doc(
		{
			"doctype": "Participant Profile",
			"participant": TEST_PARTICIPANT_NAME,
			"legally_competent": "Yes",
			"marital_status": "Single",
			"living_arrangements": [
				{"living_arrangement": living_arrangement},
			],
			"religious_or_spiritual": "No",
			"religion": "No Religion",
			"cald": "No",
			"atsi": "Neither",
			"consent_received": [
				{"consent_type": consent_type},
			],
			"organ_cadaver_donor": "Unknown",
			"chap": "No",
			"peep": "No",
			"risk_or_alert_present": "No",
			"risk_or_alert": "Other",
			"interpreter_required": "No",
			"english_ability": "Fluent",
			"communication_supports_required": "No",
			"communication_type": "Verbal",
			"primary_disability": "Other",
			"secondary_disability": [
				{"secondary_disability": secondary_disability},
			],
			"disability_limitations": "Mild",
			"ability_to_act_in_emergency": "Yes",
			"end_of_life_plan": "No",
			"bsp_plan": "No",
			"receive_mobility_allowance": "No",
			"medicare_number": "1234567890",
			"crn_number": "R1-TEST-CRN",
			"private_health_care_cover": "No",
			"companion_card": "No",
			"funding_type": "Private",
			"ndia_funding_type": "Plan Managed",
			"pharmacist_name": "R1 Test Pharmacist",
			"asthma_action_plan": "N/A",
			"ascia_action_plans": "N/A",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_test_support_plan(participant):
	existing = frappe.db.get_value(
		"Support Plan",
		{"participant": participant, "status": "Active"},
		"name",
	)

	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Support Plan",
			"participant": participant,
			"plan_name": "R1 Test Support Plan",
			"status": "Active",
			"start_date": today(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def assert_care_doctype_metadata(test_case, doctype):
	meta = frappe.get_meta(doctype)
	test_case.assertEqual(meta.name, doctype)
	test_case.assertEqual(meta.module, "Care Management")
	test_case.assertFalse(meta.custom)
