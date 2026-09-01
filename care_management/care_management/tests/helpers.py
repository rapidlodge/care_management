import re

import frappe
from frappe.utils import today
from frappe.utils import add_days, nowdate


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


R2C3B_TEST_PREFIX = "R2C3B"


def _r2c3b_slug(value):
	slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
	if not slug:
		raise ValueError("R2C3B test identifier must produce a non-empty slug")
	return slug


def make_r2c3b_test_user_email(label):
	return f"r2c3b-{_r2c3b_slug(label)}@example.test"


def clear_r2c3b_permission_caches(*users):
	for user in users:
		if user:
			frappe.clear_cache(user=user)


def ensure_r2c3b_user(label, roles=(), enabled=1, user_type="System User"):
	email = make_r2c3b_test_user_email(label)
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": f"R2C3B {label}",
				"enabled": enabled,
				"user_type": user_type,
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)

	user.enabled = enabled
	user.user_type = user_type
	existing_roles = {row.role for row in user.roles}
	for role in roles:
		if role not in existing_roles:
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	clear_r2c3b_permission_caches(user.name)
	return user.name


def ensure_r2c3b_participant(label, medicare_number):
	return ensure_r2c1_participant(f"R2C3B {label}", medicare_number)


def ensure_r2c3b_user_permission(user, participant, applicable_for=None):
	return ensure_r2c1_user_permission(user, participant, applicable_for=applicable_for)


def ensure_r2c3b_support_plan(participant, label):
	return ensure_r2c1_support_plan(participant, f"R2C3B {label}")


def ensure_r2c3b_support_task(support_plan, label, user=None, status="Active", category="Personal Care"):
	name = ensure_r2c1_support_task(support_plan, f"R2C3B {label}", status=status)
	task = frappe.get_doc("Support Task", name)
	task.task_category = category
	task.status = status
	if not task.schedule_rules:
		task.append(
			"schedule_rules",
			{
				"scheduled_time": "09:00:00",
				"recurrence_type": "Daily",
				"start_date": nowdate(),
				"is_floating": 0,
			},
		)
	task.save(ignore_permissions=True)
	if user:
		ensure_r2c1_task_assignment(name, user)
	return name


def ensure_r2c3b_execution(task, status="Pending", follow_up_required=0):
	existing = frappe.db.get_value(
		"Support Task Execution Instance",
		{"support_task": task, "scheduled_date": nowdate(), "scheduled_time": "09:00:00"},
		"name",
	)
	if existing:
		frappe.db.set_value(
			"Support Task Execution Instance",
			existing,
			{
				"status": status,
				"follow_up_required": follow_up_required,
				"execution_notes": "R2C3B synthetic follow-up note" if follow_up_required else None,
			},
		)
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Support Task Execution Instance",
			"support_task": task,
			"scheduled_date": nowdate(),
			"scheduled_time": "09:00:00",
			"status": status,
			"follow_up_required": follow_up_required,
			"execution_notes": "R2C3B synthetic follow-up note" if follow_up_required else None,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_r2c3b_manager_follow_up(execution, task, participant, assigned_to):
	existing = frappe.db.get_value(
		"Manager Follow-up",
		{"execution_instance": execution, "status": "Open"},
		"name",
	)
	if existing:
		return existing
	doc = frappe.get_doc(
		{
			"doctype": "Manager Follow-up",
			"execution_instance": execution,
			"support_task": task,
			"participant": participant,
			"follow_up_reason": "Other",
			"priority": "Medium",
			"description": "R2C3B synthetic follow-up",
			"assigned_to": assigned_to,
			"due_date": add_days(today(), 1),
			"status": "Open",
			"created_from_dashboard": 1,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def ensure_r2c3b_custom_care_plan(participant, label, status="Draft", supervisor=None):
	existing = frappe.db.get_value(
		"Custom Care Plan",
		{"participant": participant, "plan_name": f"{R2C3B_TEST_PREFIX} Care Plan {label}"},
		"name",
	)
	if existing:
		doc = frappe.get_doc("Custom Care Plan", existing)
		doc.status = status
		doc.save(ignore_permissions=True)
		return doc.name
	doc = frappe.get_doc(
		{
			"doctype": "Custom Care Plan",
			"plan_name": f"{R2C3B_TEST_PREFIX} Care Plan {label}",
			"participant": participant,
			"category": "Daily Living",
			"status": status,
			"start_date": today(),
			"assigned_supervisor": supervisor,
			"purpose_and_goals": "R2C3B synthetic goal",
			"activities": [
				{
					"activity_name": "R2C3B synthetic activity",
					"activity_category": "Daily Living",
					"priority": "Medium",
					"is_active": 1,
					"frequency": "Daily",
					"scheduled_time": "09:00:00",
					"expected_duration_minutes": 15,
					"staff_count_required": 1,
					"days_of_week": "Monday",
					"instructions": "R2C3B synthetic instructions",
				}
			],
		}
	)
	doc.insert(ignore_permissions=True)
	return doc.name


def make_r3c2_user_permission(user, participant, applicable_for):
	return ensure_r2c1_user_permission(user, participant, applicable_for=applicable_for)


def r3c2_prn_item_payload(label="PRN", controlled=False, route="Oral"):
	return {
		"medication_name": f"R3C2 {label} Medication",
		"prescribed_dose": "1",
		"dose_unit": "tablet",
		"route": route,
		"time_slot": "8 AM",
		"scheduled_time": "08:00:00",
		"frequency": "Daily",
		"indication": "R3C2 scheduled purpose",
		"is_prn": 1,
		"is_controlled_drug": 1 if controlled else 0,
		"is_active": 1,
		"prn_indication": "R3C2 PRN indication",
		"prn_minimum_interval_hours": 4,
		"prn_maximum_dose": "2",
		"prn_review_due_minutes": 60,
	}


def r3c2_controlled_item_payload(label="Controlled", route="Oral"):
	data = r3c2_prn_item_payload(label=label, controlled=True, route=route)
	data["is_prn"] = 0
	return data
