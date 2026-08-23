"""Participant authorization foundation for Care Management."""

from types import MappingProxyType

import frappe


SYSTEM_MANAGER_ROLE = "System Manager"
CARE_MANAGER_ROLE = "Care Manager"
SUPPORT_COORDINATOR_ROLE = "Support Coordinator"
SUPPORT_WORKER_ROLE = "Support Worker"

CARE_MANAGER_ROLES = frozenset({SYSTEM_MANAGER_ROLE, CARE_MANAGER_ROLE})
CARE_COORDINATION_ROLES = frozenset({CARE_MANAGER_ROLE, SUPPORT_COORDINATOR_ROLE})
SUPPORT_WORKER_ROLES = frozenset({SUPPORT_WORKER_ROLE})

DIRECT_PARTICIPANT_FIELDS = MappingProxyType(
	{
		"Appointment Schedule": "participant",
		"Custom Care Plan": "participant",
		"Daily Bowel Record Chart": "participant",
		"Daily Cleaning Task Checklist": "participant",
		"Daily Food Diary": "participant",
		"Daily Shift Task Checklist": "participant",
		"Discarded Medication Register": "participant",
		"Epilepsy Management Plan": "participant",
		"Falls Risk Plan": "participant_name",
		"Fluid Intake Output Chart": "participant",
		"Hospital Support Plan": "participant",
		"Incident": "participant",
		"Manager Follow-up": "participant",
		"Medical Report Summary": "participant",
		"Medication Administration Log": "participant",
		"Mood Tracker": "participant",
		"Participant Drug Count": "participant",
		"Seizure Chart": "participant",
		"Shift Handover Item": "participant",
		"Shift Medication Check": "participant",
		"Shower Chart": "participant",
		"Skin Integrity Form": "participant",
		"Sleep Tracker": "participant",
		"Support Plan": "participant",
		"Weekly Exercise Record": "participant",
		"Weekly Meal Planner": "participant_name",
	}
)


INDIRECT_PARTICIPANT_PATHS = MappingProxyType(
	{
		"Support Task": ("support_plan", "Support Plan"),
		"Support Task Execution Instance": ("support_task", "Support Task"),
		"Support Task Delivery Log": ("execution_instance", "Support Task Execution Instance"),
		"Support Task Missed Log": ("execution_instance", "Support Task Execution Instance"),
	}
)

CHILD_PARTICIPANT_PARENTFIELDS = MappingProxyType(
	{
		"Support Task Assigned Staff": ("Support Task", "assigned_staff_table"),
		"Support Task Schedule Rule": ("Support Task", "schedule_rules"),
	}
)

RESOLVABLE_PARTICIPANT_DOCTYPES = frozenset(
	DIRECT_PARTICIPANT_FIELDS.keys()
	| INDIRECT_PARTICIPANT_PATHS.keys()
	| CHILD_PARTICIPANT_PARENTFIELDS.keys()
)

MAX_RESOLUTION_DEPTH = 8


def _get_session_user():
	return getattr(getattr(frappe, "session", None), "user", None)


def _normalize_applicable_for(applicable_for):
	return str(applicable_for or "").strip() or None


def normalize_user(user=None):
	resolved_user = user if user is not None else _get_session_user()
	resolved_user = str(resolved_user or "").strip()
	if not resolved_user or resolved_user == "Guest":
		return None
	return resolved_user


def is_guest(user=None):
	return normalize_user(user) is None


def is_administrator(user=None):
	return normalize_user(user) == "Administrator"


def is_system_manager(user=None):
	return has_any_role({SYSTEM_MANAGER_ROLE}, user=user)


def has_any_role(roles, user=None):
	resolved_user = normalize_user(user)
	if not resolved_user:
		return False
	if isinstance(roles, str):
		role_set = frozenset({roles})
	else:
		role_set = frozenset(roles or ())
	if not role_set:
		return False
	return bool(role_set.intersection(frappe.get_roles(resolved_user)))


def require_any_role(roles, user=None):
	if not has_any_role(roles, user=user):
		raise frappe.PermissionError
	return True


def get_user_participant_grants(user=None, applicable_for=None):
	resolved_user = normalize_user(user)
	if not resolved_user:
		return frozenset()
	applicable_for = _normalize_applicable_for(applicable_for)

	rows = frappe.get_all(
		"User Permission",
		filters={
			"user": resolved_user,
			"allow": "Participant Profile",
		},
		fields=["for_value", "applicable_for", "apply_to_all_doctypes"],
		order_by="for_value asc",
	)

	grants = set()
	for row in rows:
		participant = row.get("for_value")
		if not participant:
			continue
		if row.get("apply_to_all_doctypes"):
			grants.add(participant)
			continue
		if not applicable_for or row.get("applicable_for") != applicable_for:
			continue
		grants.add(participant)

	return frozenset(sorted(grants))


def has_participant_access(participant, user=None, administrative=False, applicable_for=None):
	participant = str(participant or "").strip()
	resolved_user = normalize_user(user)
	if not participant or not resolved_user:
		return False
	if administrative and (is_administrator(resolved_user) or is_system_manager(resolved_user)):
		return True
	return participant in get_user_participant_grants(resolved_user, applicable_for=applicable_for)


def require_participant_access(participant, user=None, administrative=False, applicable_for=None):
	if not has_participant_access(
		participant,
		user=user,
		administrative=administrative,
		applicable_for=applicable_for,
	):
		raise frappe.PermissionError
	return True


def resolve_participant(doctype, doc_or_name):
	return _resolve_participant(doctype, doc_or_name, depth=0, visited=frozenset())


def _resolve_participant(doctype, doc_or_name, depth, visited):
	doctype = str(doctype or "").strip()
	if not doctype or doc_or_name in (None, "") or depth > MAX_RESOLUTION_DEPTH:
		return None
	if doctype not in RESOLVABLE_PARTICIPANT_DOCTYPES:
		return None
	if not _declared_doctype_matches(doctype, doc_or_name):
		return None

	name = _document_name(doc_or_name)
	visit_key = (doctype, name or id(doc_or_name))
	if visit_key in visited:
		return None
	visited = visited.union({visit_key})

	if doctype in DIRECT_PARTICIPANT_FIELDS:
		return _field_value(doctype, doc_or_name, DIRECT_PARTICIPANT_FIELDS[doctype])

	if doctype in INDIRECT_PARTICIPANT_PATHS:
		link_field, linked_doctype = INDIRECT_PARTICIPANT_PATHS[doctype]
		linked_name = _field_value(doctype, doc_or_name, link_field)
		if not linked_name or not frappe.db.exists(linked_doctype, linked_name):
			return None
		return _resolve_participant(linked_doctype, linked_name, depth + 1, visited)

	if doctype in CHILD_PARTICIPANT_PARENTFIELDS:
		parenttype = _field_value(doctype, doc_or_name, "parenttype")
		parent = _field_value(doctype, doc_or_name, "parent")
		parentfield = _field_value(doctype, doc_or_name, "parentfield")
		if parenttype and parent and parentfield:
			expected = CHILD_PARTICIPANT_PARENTFIELDS[doctype]
			if expected != (parenttype, parentfield):
				return None
			return _resolve_participant(parenttype, parent, depth + 1, visited)

	return None


def _document_name(doc_or_name):
	if isinstance(doc_or_name, str):
		return doc_or_name
	if isinstance(doc_or_name, dict):
		return doc_or_name.get("name")
	return getattr(doc_or_name, "name", None)


def _declared_doctype(doc_or_name):
	if isinstance(doc_or_name, str):
		return None
	if isinstance(doc_or_name, dict):
		return doc_or_name.get("doctype")
	return getattr(doc_or_name, "doctype", None)


def _declared_doctype_matches(expected_doctype, doc_or_name):
	if isinstance(doc_or_name, str):
		return True
	return _declared_doctype(doc_or_name) == expected_doctype


def _field_value(doctype, doc_or_name, fieldname):
	if isinstance(doc_or_name, dict):
		return doc_or_name.get(fieldname)
	if not isinstance(doc_or_name, str):
		if hasattr(doc_or_name, "get"):
			return doc_or_name.get(fieldname)
		return getattr(doc_or_name, fieldname, None)
	return frappe.db.get_value(doctype, doc_or_name, fieldname)


def _task_name(task):
	if not _declared_doctype_matches("Support Task", task):
		return None
	if isinstance(task, str):
		return task.strip() or None
	return _document_name(task)


def _get_authoritative_task_context(task):
	task_name = _task_name(task)
	if not task_name:
		return None
	row = frappe.db.get_value(
		"Support Task",
		task_name,
		["name", "status", "support_plan"],
		as_dict=True,
	)
	if not row or not row.get("name") or not row.get("support_plan"):
		return None
	return row


def has_task_assignment(task, user=None):
	task_context = _get_authoritative_task_context(task)
	resolved_user = normalize_user(user)
	if not task_context or not resolved_user:
		return False
	return bool(
		frappe.db.exists(
			"Support Task Assigned Staff",
			{
				"parent": task_context.name,
				"parenttype": "Support Task",
				"parentfield": "assigned_staff_table",
				"staff_user": resolved_user,
			},
		)
	)


def can_access_task(task, user=None, administrative=False):
	resolved_user = normalize_user(user)
	if not resolved_user:
		return False
	if not has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user):
		return False
	task_context = _get_authoritative_task_context(task)
	if not task_context or task_context.status != "Active":
		return False
	participant = resolve_participant("Support Task", task_context.name)
	if not has_participant_access(
		participant,
		user=resolved_user,
		applicable_for="Support Task",
	):
		return False
	return has_task_assignment(task_context.name, user=resolved_user)


def require_task_action_access(task, user=None):
	if not can_access_task(task, user=user):
		raise frappe.PermissionError
	return True
