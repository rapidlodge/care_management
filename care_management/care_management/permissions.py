"""Participant authorization foundation for Care Management."""

from contextlib import contextmanager
from contextvars import ContextVar
from types import MappingProxyType

import frappe


SYSTEM_MANAGER_ROLE = "System Manager"
CARE_MANAGER_ROLE = "Care Manager"
SUPPORT_COORDINATOR_ROLE = "Support Coordinator"
SUPPORT_WORKER_ROLE = "Support Worker"

CARE_MANAGER_ROLES = frozenset({SYSTEM_MANAGER_ROLE, CARE_MANAGER_ROLE})
CARE_COORDINATION_ROLES = frozenset({CARE_MANAGER_ROLE, SUPPORT_COORDINATOR_ROLE})
SUPPORT_WORKER_ROLES = frozenset({SUPPORT_WORKER_ROLE})
MANAGER_ENDPOINT_ROLES = frozenset({SYSTEM_MANAGER_ROLE, CARE_MANAGER_ROLE})
SCHEDULE_READ_ROLES = frozenset(
	{SYSTEM_MANAGER_ROLE, CARE_MANAGER_ROLE, SUPPORT_COORDINATOR_ROLE, SUPPORT_WORKER_ROLE}
)

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
		"Medication Administration Event": "participant",
		"Medication Event Addendum": "participant",
		"Medication PRN Effectiveness Review": "participant",
		"Controlled Medication Transaction": "participant",
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
SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES = frozenset(
	{
		"Medication Administration Event",
		"Medication Event Addendum",
		"Medication PRN Effectiveness Review",
		"Participant Drug Count",
		"Shift Medication Check",
		"Discarded Medication Register",
		"Incident",
	}
)

MAX_RESOLUTION_DEPTH = 8
_CONTROLLED_TRANSACTION_SOURCE_CONTEXT = ContextVar(
	"care_management_controlled_transaction_source_context",
	default=None,
)


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


def is_enabled_system_user(user=None):
	resolved_user = normalize_user(user)
	if not resolved_user:
		return False
	if resolved_user == "Administrator":
		return True
	row = frappe.db.get_value("User", resolved_user, ["enabled", "user_type"], as_dict=True)
	return bool(row and row.enabled and row.user_type == "System User")


def require_enabled_system_user(user=None):
	resolved_user = normalize_user(user)
	if not resolved_user or not is_enabled_system_user(resolved_user):
		raise frappe.PermissionError
	return resolved_user


def require_manager_endpoint_access(user=None):
	resolved_user = require_enabled_system_user(user)
	if not has_any_role(MANAGER_ENDPOINT_ROLES, user=resolved_user):
		raise frappe.PermissionError
	return resolved_user


def require_schedule_read_access(user=None):
	resolved_user = require_enabled_system_user(user)
	if not has_any_role(SCHEDULE_READ_ROLES, user=resolved_user):
		raise frappe.PermissionError
	return resolved_user


def get_authorized_participants(user=None, doctype=None, administrative=False):
	resolved_user = require_enabled_system_user(user)
	if administrative and _is_participant_boundary_administrator(resolved_user):
		return None
	grants = get_user_participant_grants(resolved_user, applicable_for=doctype)
	if not grants:
		raise frappe.PermissionError
	return frozenset(grants)


def require_endpoint_participant_access(participant, user=None, doctype=None, administrative=False):
	resolved_user = require_enabled_system_user(user)
	require_participant_access(
		participant,
		user=resolved_user,
		administrative=administrative,
		applicable_for=doctype,
	)
	return resolved_user


def require_standard_document_permission(doctype, ptype, doc=None, user=None):
	resolved_user = require_enabled_system_user(user)
	if not frappe.has_permission(doctype, ptype, doc=doc, user=resolved_user):
		raise frappe.PermissionError
	return resolved_user


def task_participant(task):
	return resolve_participant("Support Task", task)


def require_worker_task_action(task, user=None):
	resolved_user = require_enabled_system_user(user)
	require_task_action_access(task, user=resolved_user)
	return resolved_user


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


@contextmanager
def controlled_transaction_source_context(source):
	"""Authorize one nested controlled-transaction source workflow."""
	token = _CONTROLLED_TRANSACTION_SOURCE_CONTEXT.set(frappe._dict(source or {}))
	try:
		yield
	finally:
		_CONTROLLED_TRANSACTION_SOURCE_CONTEXT.reset(token)


def get_controlled_transaction_source_context():
	return _CONTROLLED_TRANSACTION_SOURCE_CONTEXT.get()


def has_controlled_transaction_source_context():
	return bool(get_controlled_transaction_source_context())


def _is_participant_boundary_administrator(user):
	return is_administrator(user) or is_system_manager(user)


def _has_participant_document_role(doctype, user):
	if has_any_role(STANDARD_DOCUMENT_ACCESS_ROLES, user=user):
		return True
	return doctype in SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES and has_any_role(
		SUPPORT_WORKER_ROLES,
		user=user,
	)


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
	if doctype == "Medication Event Addendum":
		participant = _field_value(doctype, doc, "participant")
		if participant:
			return participant
		medication_event = _field_value(doctype, doc, "medication_event")
		if medication_event:
			return resolve_participant("Medication Administration Event", medication_event)
	return resolve_participant(doctype, doc)


def has_participant_document_permission(doc, ptype=None, user=None, debug=False):
	doctype = _doc_doctype(doc)
	resolved_user = normalize_user(user)
	permission_type = str(ptype or "read").strip().lower()
	if not doctype or doctype not in PROTECTED_PARTICIPANT_DOCTYPES:
		return False
	if not resolved_user:
		return False
	if _is_participant_boundary_administrator(resolved_user):
		return True
	source_controlled_write = (
		doctype == "Controlled Medication Transaction"
		and permission_type in {"create", "write", "submit"}
		and has_controlled_transaction_source_context()
	)
	if not source_controlled_write and not _has_participant_document_role(doctype, resolved_user):
		return False
	if doctype == "Controlled Medication Transaction":
		if (
			not source_controlled_write
			and has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user)
			and not has_any_role(STANDARD_DOCUMENT_ACCESS_ROLES, user=resolved_user)
		):
			return False
	if doctype == "Participant Profile" and permission_type == "create":
		return True
	if (
		not source_controlled_write
		and has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user)
		and not has_any_role(STANDARD_DOCUMENT_ACCESS_ROLES, user=resolved_user)
	):
		if not _support_worker_document_permission_allowed(doctype, doc, permission_type, resolved_user):
			return False

	participant = _resolve_protected_document_participant(doctype, doc)
	if not participant:
		return False
	applicable_for = doctype
	if source_controlled_write:
		context = get_controlled_transaction_source_context()
		applicable_for = context.get("source_doctype") if context else doctype
	return has_participant_access(participant, user=resolved_user, applicable_for=applicable_for)


def _support_worker_document_permission_allowed(doctype, doc, permission_type, user):
	if doctype == "Medication Administration Event":
		return permission_type in {"create", "read", "select", "write", "submit"}
	if doctype == "Medication Event Addendum":
		if permission_type == "create":
			return True
		if permission_type in {"read", "select", "write"}:
			return _addendum_owned_by_worker(doc, user)
		return False
	if doctype == "Medication PRN Effectiveness Review":
		if permission_type == "create":
			return True
		if permission_type in {"create", "read", "select", "write"}:
			return _prn_review_owned_by_worker(doc, user)
		return False
	if doctype in {"Participant Drug Count", "Shift Medication Check", "Discarded Medication Register"}:
		if permission_type == "create":
			return True
		return permission_type in {"create", "read", "select", "write"} and _draft_owned_by_worker(
			doctype, doc, user
		)
	if doctype == "Incident":
		if permission_type == "create":
			return True
		return permission_type in {"read", "select", "write"} and _incident_owned_by_reporter(doc, user)
	return False


def _prn_review_owned_by_worker(doc, user):
	name = _doc_name(doc)
	if not name:
		return False
	if isinstance(doc, str):
		return frappe.db.get_value("Medication PRN Effectiveness Review", name, "administering_worker") == user
	return _field_value("Medication PRN Effectiveness Review", doc, "administering_worker") == user


def _addendum_owned_by_worker(doc, user):
	name = _doc_name(doc)
	if not name:
		return False
	if isinstance(doc, str):
		return frappe.db.get_value("Medication Event Addendum", name, "created_by") == user
	return _field_value("Medication Event Addendum", doc, "created_by") == user


def _draft_owned_by_worker(doctype, doc, user):
	name = _doc_name(doc)
	if not name:
		return False
	owner_field = {
		"Participant Drug Count": "observed_by",
		"Shift Medication Check": "checked_by",
		"Discarded Medication Register": "prepared_by",
	}.get(doctype)
	if not owner_field:
		return False
	row = frappe.db.get_value(doctype, name, [owner_field, "docstatus"], as_dict=True)
	return bool(row and row.get(owner_field) == user and row.docstatus == 0)


def _incident_owned_by_reporter(doc, user):
	name = _doc_name(doc)
	if not name:
		return False
	row = frappe.db.get_value("Incident", name, ["reported_by", "incident_status"], as_dict=True)
	return bool(row and row.reported_by == user and row.incident_status == "Open")


def _sql_table(doctype):
	return f"`tab{doctype}`"


def _sql_value(value):
	return frappe.db.escape(value)


def _sql_in(values):
	values = tuple(sorted(str(value) for value in values if value))
	if not values:
		return None
	return ", ".join(_sql_value(value) for value in values)


def _search_inputs(doctype, txt, searchfield, start, page_len, expected_doctype, allowed_searchfields):
	if doctype != expected_doctype:
		return None
	if searchfield not in allowed_searchfields:
		return None
	try:
		start = int(start or 0)
		page_len = int(page_len or 20)
	except (TypeError, ValueError):
		return None
	if start < 0 or page_len <= 0 or page_len > 100:
		return None
	return frappe._dict(
		{
			"txt": str(txt or "").strip(),
			"searchfield": searchfield,
			"start": start,
			"page_len": page_len,
		}
	)


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
	if not _has_participant_document_role(doctype, resolved_user):
		return "1=0"
	grants = get_user_participant_grants(resolved_user, applicable_for=doctype)
	base_condition = _participant_query_condition(doctype, grants)
	if has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES, user=resolved_user
	):
		worker_condition = _support_worker_query_condition(doctype, resolved_user)
		if worker_condition is None:
			return "1=0"
		if worker_condition == "":
			return base_condition
		return f"({base_condition}) and ({worker_condition})"
	return base_condition


def _support_worker_query_condition(doctype, user):
	table = _sql_table(doctype)
	escaped_user = _sql_value(user)
	if doctype == "Medication Administration Event":
		return ""
	if doctype == "Medication Event Addendum":
		return f"{table}.`created_by` = {escaped_user}"
	if doctype == "Medication PRN Effectiveness Review":
		return f"{table}.`administering_worker` = {escaped_user}"
	if doctype == "Participant Drug Count":
		return f"{table}.`observed_by` = {escaped_user} and {table}.`docstatus` = 0"
	if doctype == "Shift Medication Check":
		return f"{table}.`checked_by` = {escaped_user} and {table}.`docstatus` = 0"
	if doctype == "Discarded Medication Register":
		return f"{table}.`prepared_by` = {escaped_user} and {table}.`docstatus` = 0"
	if doctype == "Incident":
		return f"{table}.`reported_by` = {escaped_user} and {table}.`incident_status` = 'Open'"
	return None


def search_applicable_participants(
	doctype,
	txt,
	searchfield,
	start,
	page_len,
	applicable_for,
	filters=None,
	allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES,
):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Participant Profile", {"name", "participant"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		allowed_roles,
		user=resolved_user,
	):
		return []

	values = None
	if not _is_participant_boundary_administrator(resolved_user):
		values = _sql_in(
			get_user_participant_grants(
				resolved_user,
				applicable_for=applicable_for,
			)
		)
		if not values:
			return []

	conditions = ["`disabled` = 0"] if frappe.get_meta("Participant Profile").has_field("disabled") else []
	if values:
		conditions.append(f"`name` in ({values})")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"(`name` like {like_value} or `participant` like {like_value})")
	where_clause = " and ".join(conditions) if conditions else "1=1"

	return frappe.db.sql(
		f"""
		select `name`, `participant`
		from `tabParticipant Profile`
		where {where_clause}
		order by
			case when `{search.searchfield}` = %s then 0 else 1 end,
			`participant` asc,
			`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_medication_log_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Medication Administration Log",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES,
	)


def search_medication_event_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Medication Administration Event",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


def search_medication_event_plans(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Medication Administration Log", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Medication Administration Event",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = ["medication_log.`plan_status` = 'Active'"]
	if values:
		conditions.append(f"medication_log.`participant` in ({values})")
	if has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES,
		user=resolved_user,
	):
		conditions.append(
			f"""
			exists (
				select 1
				from `tabSupport Task` support_task
				inner join `tabSupport Task Assigned Staff` assigned_staff
				on assigned_staff.`parent` = support_task.`name`
				and assigned_staff.`parenttype` = 'Support Task'
				and assigned_staff.`parentfield` = 'assigned_staff_table'
				where support_task.`source_doctype` = 'Medication Administration Log'
				and support_task.`source_docname` = medication_log.`name`
				and support_task.`status` = 'Active'
				and assigned_staff.`staff_user` = {_sql_value(resolved_user)}
			)
			"""
		)
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"medication_log.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select medication_log.`name`, medication_log.`name`
		from `tabMedication Administration Log` medication_log
		where {where_clause}
		order by
			case when medication_log.`{search.searchfield}` = %s then 0 else 1 end,
			medication_log.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_medication_event_support_tasks(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Support Task", {"name", "task_name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Medication Administration Event",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = [
		"support_task.`status` = 'Active'",
		"support_task.`source_doctype` = 'Medication Administration Log'",
	]
	if values:
		conditions.append(f"support_plan.`participant` in ({values})")
	if has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES,
		user=resolved_user,
	):
		conditions.append(
			f"""
			exists (
				select 1
				from `tabSupport Task Assigned Staff` assigned_staff
				where assigned_staff.`parent` = support_task.`name`
				and assigned_staff.`parenttype` = 'Support Task'
				and assigned_staff.`parentfield` = 'assigned_staff_table'
				and assigned_staff.`staff_user` = {_sql_value(resolved_user)}
			)
			"""
		)
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"(support_task.`name` like {like_value} or support_task.`task_name` like {like_value})")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select support_task.`name`, support_task.`task_name`
		from `tabSupport Task` support_task
		inner join `tabSupport Plan` support_plan
		on support_plan.`name` = support_task.`support_plan`
		where {where_clause}
		order by
			case when support_task.`{search.searchfield}` = %s then 0 else 1 end,
			support_task.`task_name` asc,
			support_task.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_medication_prn_review_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Medication PRN Effectiveness Review",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_event_addendum_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Medication Event Addendum",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def search_medication_event_addendum_events(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Medication Administration Event", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Medication Event Addendum",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = ["event.`docstatus` = 1"]
	if values:
		conditions.append(f"event.`participant` in ({values})")
	if has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES,
		user=resolved_user,
	):
		conditions.append(f"event.`worker` = {_sql_value(resolved_user)}")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"event.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select event.`name`, event.`name`
		from `tabMedication Administration Event` event
		where {where_clause}
		order by
			case when event.`{search.searchfield}` = %s then 0 else 1 end,
			event.`scheduled_datetime` desc,
			event.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_medication_prn_review_events(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Medication Administration Event", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Medication PRN Effectiveness Review",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = [
		"event.`docstatus` = 1",
		"event.`outcome` = 'Administered'",
		"event.`is_prn_snapshot` = 1",
	]
	if values:
		conditions.append(f"event.`participant` in ({values})")
	if has_any_role(SUPPORT_WORKER_ROLES, user=resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES,
		user=resolved_user,
	):
		conditions.append(f"event.`worker` = {_sql_value(resolved_user)}")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"event.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select event.`name`, event.`name`
		from `tabMedication Administration Event` event
		where {where_clause}
		order by
			case when event.`{search.searchfield}` = %s then 0 else 1 end,
			event.`scheduled_datetime` desc,
			event.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_medication_prn_review_plans(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Medication Administration Log", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Medication PRN Effectiveness Review",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = ["medication_log.`plan_status` = 'Active'"]
	if values:
		conditions.append(f"medication_log.`participant` in ({values})")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"medication_log.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select medication_log.`name`, medication_log.`name`
		from `tabMedication Administration Log` medication_log
		where {where_clause}
		order by
			case when medication_log.`{search.searchfield}` = %s then 0 else 1 end,
			medication_log.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_controlled_transaction_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Controlled Medication Transaction",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES,
	)


def search_controlled_transaction_plans(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Medication Administration Log", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Controlled Medication Transaction",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = ["medication_log.`plan_status` = 'Active'"]
	if values:
		conditions.append(f"medication_log.`participant` in ({values})")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"medication_log.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select medication_log.`name`, medication_log.`name`
		from `tabMedication Administration Log` medication_log
		where {where_clause}
		order by
			case when medication_log.`name` = %s then 0 else 1 end,
			medication_log.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_participant_drug_count_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Participant Drug Count",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


def search_shift_medication_check_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Shift Medication Check",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


def search_shift_medication_check_reconciliations(doctype, txt, searchfield, start, page_len, filters=None):
	search = _search_inputs(doctype, txt, searchfield, start, page_len, "Participant Drug Count", {"name"})
	if not search:
		return []
	resolved_user = normalize_user()
	if not resolved_user:
		return []
	if not _is_participant_boundary_administrator(resolved_user) and not has_any_role(
		STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
		user=resolved_user,
	):
		return []

	grants = get_user_participant_grants(
		resolved_user,
		applicable_for="Shift Medication Check",
	)
	values = _sql_in(grants)
	if not _is_participant_boundary_administrator(resolved_user) and not values:
		return []

	conditions = [
		"drug_count.`docstatus` = 1",
		"drug_count.`reconciliation_status` = 'Reconciled'",
	]
	if values:
		conditions.append(f"drug_count.`participant` in ({values})")
	if filters and filters.get("participant"):
		participant = _sql_value(filters.get("participant"))
		conditions.append(f"drug_count.`participant` = {participant}")
	if search.txt:
		like_value = _sql_value(f"%{search.txt}%")
		conditions.append(f"drug_count.`name` like {like_value}")
	where_clause = " and ".join(conditions)

	return frappe.db.sql(
		f"""
		select drug_count.`name`, drug_count.`name`
		from `tabParticipant Drug Count` drug_count
		where {where_clause}
		order by
			case when drug_count.`{search.searchfield}` = %s then 0 else 1 end,
			drug_count.`modified` desc,
			drug_count.`name` asc
		limit %s, %s
		""",
		(search.txt, search.start, search.page_len),
	)


def search_discarded_medication_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Discarded Medication Register",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


def search_incident_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return search_applicable_participants(
		doctype,
		txt,
		searchfield,
		start,
		page_len,
		"Incident",
		filters=filters,
		allowed_roles=STANDARD_DOCUMENT_ACCESS_ROLES | SUPPORT_WORKER_ROLES,
	)


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
