import re

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


R2C1_TEST_PREFIX = "R2C1"


def _r2c1_email_slug(value):
	slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
	if not slug:
		raise ValueError("R2C1 test-user email label must produce a non-empty slug")
	return slug


def make_r2c1_test_user_email(label):
	return f"r2c1-{_r2c1_email_slug(label)}@example.test"


def clear_r2c1_permission_caches(user=None):
	if user:
		frappe.clear_cache(user=user)


def ensure_r2c1_participant(suffix, medicare_number):
	participant_name = f"{R2C1_TEST_PREFIX} Participant {suffix}"
	existing = frappe.db.get_value(
		"Participant Profile",
		{"participant": participant_name},
		"name",
	)

	if existing:
		return existing

	living_arrangement = _ensure_named_master(
		"Living Arrangement",
		"arrangement_name",
		f"{R2C1_TEST_PREFIX} Living Arrangement {suffix}",
	)
	consent_type = _ensure_named_master(
		"Consent Type",
		"consent_name",
		f"{R2C1_TEST_PREFIX} Consent {suffix}",
	)
	secondary_disability = _ensure_named_master(
		"Secondary Disability Type",
		"disability_name",
		f"{R2C1_TEST_PREFIX} Secondary Disability {suffix}",
	)

	doc = frappe.get_doc(
		{
			"doctype": "Participant Profile",
			"participant": participant_name,
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
			"medicare_number": medicare_number,
			"crn_number": f"{R2C1_TEST_PREFIX}-{suffix}-CRN",
			"private_health_care_cover": "No",
			"companion_card": "No",
			"funding_type": "Private",
			"ndia_funding_type": "Plan Managed",
			"pharmacist_name": f"{R2C1_TEST_PREFIX} Pharmacist {suffix}",
			"asthma_action_plan": "N/A",
			"ascia_action_plans": "N/A",
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_r2c1_user(suffix, roles):
	email = make_r2c1_test_user_email(suffix)
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"R2C1 {suffix}",
				"enabled": 1,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)

	existing_roles = {row.role for row in user.roles}
	for role in roles:
		if role not in existing_roles:
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	clear_r2c1_permission_caches(user.name)
	return user.name


def ensure_r2c1_user_permission(user, participant, applicable_for=None):
	filters = {
		"user": user,
		"allow": "Participant Profile",
		"for_value": participant,
	}
	if applicable_for:
		filters["applicable_for"] = applicable_for

	existing = frappe.db.get_value("User Permission", filters, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "User Permission",
			"user": user,
			"allow": "Participant Profile",
			"for_value": participant,
			"applicable_for": applicable_for,
			"apply_to_all_doctypes": 1 if not applicable_for else 0,
		}
	)
	doc.insert(ignore_permissions=True)
	clear_r2c1_permission_caches(user)
	return doc.name


def ensure_r2c1_support_plan(participant, suffix):
	existing = frappe.db.get_value(
		"Support Plan",
		{"participant": participant, "plan_name": f"{R2C1_TEST_PREFIX} Support Plan {suffix}"},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Support Plan",
			"participant": participant,
			"plan_name": f"{R2C1_TEST_PREFIX} Support Plan {suffix}",
			"status": "Active",
			"start_date": today(),
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_r2c1_support_task(support_plan, suffix, status="Active"):
	existing = frappe.db.get_value(
		"Support Task",
		{"support_plan": support_plan, "task_name": f"{R2C1_TEST_PREFIX} Task {suffix}"},
		"name",
	)
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "Support Task",
			"support_plan": support_plan,
			"task_name": f"{R2C1_TEST_PREFIX} Task {suffix}",
			"task_category": "Personal Care",
			"status": status,
			"clinical_priority": "Mandatory",
			"staff_count_required": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_r2c1_task_assignment(task, user):
	task_doc = frappe.get_doc("Support Task", task)
	for row in task_doc.assigned_staff_table:
		if row.staff_user == user:
			return row.name
	task_doc.append(
		"assigned_staff_table",
		{
			"staff_user": user,
			"role": "Primary Carer",
		},
	)
	task_doc.save(ignore_permissions=True)
	return task_doc.assigned_staff_table[-1].name
