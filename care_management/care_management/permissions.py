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

PROTECTED_PARTICIPANT_DOCTYPES = frozenset(
	{"Participant Profile"}
	| DIRECT_PARTICIPANT_FIELDS.keys()
	| INDIRECT_PARTICIPANT_PATHS.keys()
)

STANDARD_DOCUMENT_ACCESS_ROLES = frozenset({CARE_MANAGER_ROLE, SUPPORT_COORDINATOR_ROLE})

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


def _is_participant_boundary_administrator(user):
	return is_administrator(user) or is_system_manager(user)


def _has_standard_participant_document_role(user):
	return has_any_role(STANDARD_DOCUMENT_ACCESS_ROLES, user=user)


def _doc_doctype(doc):
	if isinstance(doc, dict):
		return str(doc.get("doctype") or "").strip()
	return str(getattr(doc, "doctype", "") or "").strip()


def _doc_name(doc):
	if isinstance(doc, str):
		return doc.strip()
	if isinstance(doc, dict):
		return str(doc.get("name") or "").strip()
	return str(getattr(doc, "name", "") or "").strip()


def _resolve_protected_document_participant(doctype, doc):
	if doctype == "Participant Profile":
		name = _doc_name(doc)
		if not name:
			return None
		if isinstance(doc, str) and not frappe.db.exists("Participant Profile", name):
			return None
		return name
	return resolve_participant(doctype, doc)


def has_participant_document_permission(doc, ptype=None, user=None, debug=False):
	doctype = _doc_doctype(doc)
	resolved_user = normalize_user(user)
	if not doctype or doctype not in PROTECTED_PARTICIPANT_DOCTYPES:
		return False
	if not resolved_user:
		return False
	if _is_participant_boundary_administrator(resolved_user):
		return True
	if not _has_standard_participant_document_role(resolved_user):
		return False
	if doctype == "Participant Profile" and str(ptype or "").strip().lower() == "create":
		return True

	participant = _resolve_protected_document_participant(doctype, doc)
	if not participant:
		return False
	return has_participant_access(participant, user=resolved_user, applicable_for=doctype)


def _sql_table(doctype):
	return f"`tab{doctype}`"


def _sql_value(value):
	return frappe.db.escape(value)


def _sql_in(values):
	values = tuple(sorted(str(value) for value in values if value))
	if not values:
		return None
	return ", ".join(_sql_value(value) for value in values)


def _participant_query_condition(doctype, participant_values):
	values = _sql_in(participant_values)
	if not values:
		return "1=0"
	table = _sql_table(doctype)

	if doctype == "Participant Profile":
		return f"{table}.`name` in ({values})"

	if doctype in DIRECT_PARTICIPANT_FIELDS:
		fieldname = DIRECT_PARTICIPANT_FIELDS[doctype]
		return f"{table}.`{fieldname}` in ({values})"

	if doctype == "Support Task":
		return (
			"exists ("
			"select 1 from `tabSupport Plan` support_plan "
			f"where support_plan.`name` = {table}.`support_plan` "
			f"and support_plan.`participant` in ({values})"
			")"
		)

	if doctype == "Support Task Execution Instance":
		return (
			"exists ("
			"select 1 from `tabSupport Task` support_task "
			"inner join `tabSupport Plan` support_plan "
			"on support_plan.`name` = support_task.`support_plan` "
			f"where support_task.`name` = {table}.`support_task` "
			f"and support_plan.`participant` in ({values})"
			")"
		)

	if doctype in {"Support Task Delivery Log", "Support Task Missed Log"}:
		return (
			"exists ("
			"select 1 from `tabSupport Task Execution Instance` execution_instance "
			"inner join `tabSupport Task` support_task "
			"on support_task.`name` = execution_instance.`support_task` "
			"inner join `tabSupport Plan` support_plan "
			"on support_plan.`name` = support_task.`support_plan` "
			f"where execution_instance.`name` = {table}.`execution_instance` "
			f"and support_plan.`participant` in ({values})"
			")"
		)

	return "1=0"


def get_participant_permission_query_conditions(doctype, user=None):
	doctype = str(doctype or "").strip()
	resolved_user = normalize_user(user)
	if doctype not in PROTECTED_PARTICIPANT_DOCTYPES or not resolved_user:
		return "1=0"
	if _is_participant_boundary_administrator(resolved_user):
		return ""
	if not _has_standard_participant_document_role(resolved_user):
		return "1=0"
	grants = get_user_participant_grants(resolved_user, applicable_for=doctype)
	return _participant_query_condition(doctype, grants)


def permission_query_condition_method_name(doctype):
	suffix = (
		str(doctype or "")
		.strip()
		.lower()
		.replace("-", "_")
		.replace("/", "_")
		.replace(" ", "_")
	)
	return f"get_{suffix}_permission_query_conditions"


def _make_permission_query_condition(bound_doctype):
	def _permission_query_conditions(user=None, doctype=None):
		requested_doctype = str(doctype or bound_doctype).strip()
		if requested_doctype != bound_doctype:
			return "1=0"
		return get_participant_permission_query_conditions(bound_doctype, user=user)

	_permission_query_conditions.__name__ = permission_query_condition_method_name(bound_doctype)
	return _permission_query_conditions


for _participant_doctype in sorted(PROTECTED_PARTICIPANT_DOCTYPES):
	globals()[permission_query_condition_method_name(_participant_doctype)] = _make_permission_query_condition(
		_participant_doctype
	)


PARTICIPANT_PERMISSION_QUERY_CONDITION_HOOKS = MappingProxyType(
	{
		doctype: f"care_management.care_management.permissions.{permission_query_condition_method_name(doctype)}"
		for doctype in sorted(PROTECTED_PARTICIPANT_DOCTYPES)
	}
)

PARTICIPANT_DOCUMENT_PERMISSION_HOOKS = MappingProxyType(
	{
		doctype: "care_management.care_management.permissions.has_participant_document_permission"
		for doctype in sorted(PROTECTED_PARTICIPANT_DOCTYPES)
	}
)


def _docshare_user_is_shareable(user):
	raw_user = str(user or "").strip()
	if not raw_user:
		return False

	resolved_user = normalize_user(raw_user)
	if not resolved_user:
		return False
	user_row = frappe.db.get_value("User", resolved_user, ["enabled", "user_type"], as_dict=True)
	if not user_row:
		return False
	return bool(user_row.enabled) and user_row.user_type == "System User"


def validate_participant_docshare(doc, method=None):
	share_doctype = str(doc.get("share_doctype") if hasattr(doc, "get") else getattr(doc, "share_doctype", "")).strip()
	if share_doctype not in PROTECTED_PARTICIPANT_DOCTYPES:
		return None

	share_name = doc.get("share_name") if hasattr(doc, "get") else getattr(doc, "share_name", None)
	share_user = doc.get("user") if hasattr(doc, "get") else getattr(doc, "user", None)
	everyone = doc.get("everyone") if hasattr(doc, "get") else getattr(doc, "everyone", None)
	share_user_value = str(share_user or "").strip()
	if everyone or not share_user_value or not _docshare_user_is_shareable(share_user_value):
		raise frappe.PermissionError
	if not share_name or not frappe.db.exists(share_doctype, share_name):
		raise frappe.PermissionError

	shared_doc = frappe.get_doc(share_doctype, share_name)
	if not has_participant_document_permission(shared_doc, "read", share_user_value):
		raise frappe.PermissionError
	return None
