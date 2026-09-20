"""Participant-scoped medication audit evidence export."""

import hashlib
import io
import json
import posixpath
import zipfile
from datetime import date, datetime

import frappe
from frappe.utils import getdate, now_datetime
from frappe.utils.file_manager import get_content_hash, get_file_path

from care_management.care_management import permissions

EXPORT_SCHEMA_VERSION = "R3G-1"
EXPORT_DOCTYPE = "Medication Administration Log"
EXPORT_ROLES = frozenset({"Care Manager", "System Manager"})
MAX_EXPORT_RECORDS_PER_DOCTYPE = 500
MAX_EXPORT_ATTACHMENTS = 1000
MAX_EXPORT_VERSIONS = 5000
MAX_EXPORT_UNCOMPRESSED_BYTES = 25 * 1024 * 1024

CHILD_DATE_SCOPE_RULE = (
	"Parents are selected when at least one child date intersects the requested range; "
	"every selected parent is exported with its complete child evidence."
)

MEDICATION_RECORD_ALLOWLISTS = {
	"Medication Administration Log": (
		"name",
		"participant",
		"week_commencing",
		"plan_status",
		"plan_version",
		"effective_from",
		"effective_to",
		"review_date",
		"previous_plan",
		"replacement_plan",
		"approved_by",
		"approved_on",
		"purpose_evidence_status",
		"change_reason",
		"lifecycle_reason",
	),
	"Medication Plan Item": (
		"name",
		"parent",
		"parenttype",
		"parentfield",
		"medication_name",
		"prescribed_dose",
		"dose_unit",
		"route",
		"frequency",
		"scheduled_time",
		"indication",
		"is_prn",
		"is_controlled_drug",
		"is_active",
		"prn_indication",
		"prn_minimum_interval_hours",
		"prn_maximum_dose",
		"prn_review_due_minutes",
	),
	"Medication Administration Event": (
		"name",
		"participant",
		"medication_plan",
		"medication_plan_item",
		"support_task",
		"execution_instance",
		"scheduled_datetime",
		"actual_datetime",
		"worker",
		"finalized_by",
		"finalized_on",
		"occurrence_key",
		"prescribed_dose",
		"administered_dose",
		"dose_unit",
		"route",
		"outcome",
		"variance_reason",
		"checker",
		"prn_indication",
		"is_prn_snapshot",
		"is_controlled_drug_snapshot",
		"prn_review_due_at",
		"controlled_transaction",
		"incident",
	),
	"Medication Event Addendum": (
		"name",
		"medication_event",
		"participant",
		"medication_plan",
		"medication_plan_item",
		"event_worker",
		"event_scheduled_datetime",
		"event_actual_datetime",
		"original_outcome",
		"original_administered_dose",
		"original_dose_unit",
		"previous_addendum",
		"sequence_number",
		"amendment_reason",
		"correction_explanation",
		"created_by",
		"created_on",
		"review_decision",
		"review_comments",
		"reviewed_by",
		"reviewed_on",
	),
	"Medication PRN Effectiveness Review": (
		"name",
		"participant",
		"medication_event",
		"medication_plan",
		"medication_plan_item",
		"administering_worker",
		"review_due_at",
		"reviewed_at",
		"effectiveness_outcome",
		"effectiveness_notes",
		"incident",
		"finalized_by",
		"finalized_on",
	),
	"Controlled Medication Transaction": (
		"name",
		"participant",
		"medication_plan",
		"medication_plan_item",
		"posting_datetime",
		"transaction_type",
		"direction",
		"quantity",
		"dose_unit",
		"balance_before",
		"balance_after",
		"actor",
		"witness",
		"source_doctype",
		"source_docname",
		"source_action",
		"source_key",
		"reason",
		"incident",
		"reverses_transaction",
		"finalized_by",
		"finalized_on",
	),
	"Participant Drug Count": (
		"name",
		"participant",
		"observed_by",
		"webster_pak_type",
		"reconciliation_status",
		"medication_plan_item",
		"expected_balance",
		"observed_balance",
		"discrepancy_quantity",
		"discrepancy_incident",
		"reconciled_by",
		"reconciled_on",
	),
	"Drug Count Entry": (
		"name",
		"parent",
		"parenttype",
		"parentfield",
		"date",
		"staff_name",
		"medication_plan_item",
		"dose_unit",
		"expected_balance",
		"observed_balance",
		"discrepancy_quantity",
		"discrepancy_incident",
	),
	"Shift Medication Check": (
		"name",
		"participant",
		"checked_by",
		"month",
		"reconciliation",
		"finalized_by",
		"finalized_on",
	),
	"Shift Medication Check Entry": (
		"name",
		"parent",
		"parenttype",
		"parentfield",
		"date",
		"prn_given_and_signed_today",
		"medications_administered_and_signed_today",
		"any_damage_to_medication_packs",
		"reconciliation",
		"staff_name_and_signature",
	),
	"Discarded Medication Register": (
		"name",
		"participant",
		"prepared_by",
		"disposal_status",
		"finalized_by",
		"finalized_on",
	),
	"Discarded Medication Item": (
		"name",
		"parent",
		"parenttype",
		"parentfield",
		"date",
		"medication_plan_item",
		"quantity",
		"dose_unit",
		"is_controlled_drug",
		"controlled_transaction",
		"witness",
		"disposal_type",
		"discrepancy_incident",
		"incident_reported",
		"staff_disposing_medication",
		"date_of_return_to_pharmacy",
		"staff_signature_return",
	),
	"Incident": (
		"name",
		"incident_status",
		"assigned_staff",
		"reported_by",
		"reported_on",
		"participant",
		"time_of_incident",
		"date_of_incident",
		"incident_type",
		"was_rp_used",
		"severity",
		"reportable_to_commission",
		"linked_medication_event",
	),
	"File": (
		"name",
		"file_name",
		"attached_to_doctype",
		"attached_to_name",
		"is_private",
		"content_hash",
		"file_size",
		"creation",
		"owner",
	),
	"Version": (
		"name",
		"ref_doctype",
		"docname",
		"owner",
		"creation",
	),
}


def can_export_medication_audit_bundle(participant, user=None):
	try:
		require_medication_audit_export_access(participant, user=user)
	except frappe.PermissionError:
		return False
	return True


def require_medication_audit_export_access(participant, user=None):
	resolved_user = permissions.require_enabled_system_user(user)
	if not permissions.has_any_role(EXPORT_ROLES, user=resolved_user):
		raise frappe.PermissionError
	permissions.require_participant_access(
		participant,
		user=resolved_user,
		applicable_for=EXPORT_DOCTYPE,
	)
	return resolved_user


@frappe.whitelist()
def download_medication_audit_bundle(participant, from_date=None, to_date=None):
	user = permissions.normalize_user()
	bundle = build_medication_audit_bundle(participant, user=user, from_date=from_date, to_date=to_date)
	filename = _safe_filename(f"medication-audit-{participant}-{now_datetime().strftime('%Y%m%d%H%M%S')}.zip")
	frappe.local.response.filename = filename
	frappe.local.response.filecontent = bundle
	frappe.local.response.type = "binary"


@frappe.whitelist()
def can_download_medication_audit_bundle(participant):
	return can_export_medication_audit_bundle(participant, user=permissions.normalize_user())


def build_medication_audit_bundle(participant, user=None, from_date=None, to_date=None):
	participant = _require_participant(participant)
	resolved_user = require_medication_audit_export_access(participant, user=user)
	date_filters = _normalize_date_filters(from_date, to_date)
	records = _collect_medication_records(participant, date_filters)
	attachments = _collect_retained_attachment_inventory(records)
	versions = _collect_version_metadata(records)
	content_members = {
		"records.json": _json_bytes(records),
		"attachments.json": _json_bytes(attachments),
		"versions.json": _json_bytes(versions),
	}
	member_integrity = {
		name: {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
		for name, content in sorted(content_members.items())
	}
	manifest = _build_manifest(
		participant,
		resolved_user,
		date_filters,
		records,
		attachments,
		versions,
		member_integrity,
	)
	manifest["bundle_manifest_hash"] = _manifest_hash(manifest)
	members = {"manifest.json": _json_bytes(manifest), **content_members}
	_enforce_bundle_size(members)
	verify_bundle_content(manifest, members)
	return _zip_payload(members)


def _require_participant(participant):
	participant = str(participant or "").strip()
	if not participant or not frappe.db.exists("Participant Profile", participant):
		raise frappe.PermissionError
	return participant


def _normalize_date_filters(from_date, to_date):
	start = getdate(from_date) if from_date else None
	end = getdate(to_date) if to_date else None
	if start and end and end < start:
		frappe.throw("Audit export end date cannot be before start date.", frappe.ValidationError)
	return {"from_date": start, "to_date": end}


def _date_range_filter(fieldname, date_filters):
	filters = {}
	start = date_filters.get("from_date")
	end = date_filters.get("to_date")
	if start and end:
		filters[fieldname] = ["between", [start, end]]
	elif start:
		filters[fieldname] = [">=", start]
	elif end:
		filters[fieldname] = ["<=", end]
	return filters


def _collect_medication_records(participant, date_filters):
	records = {doctype: [] for doctype in MEDICATION_RECORD_ALLOWLISTS if doctype not in {"File", "Version"}}
	plans = _get_rows(
		"Medication Administration Log",
		{"participant": participant, **_date_range_filter("week_commencing", date_filters)},
	)
	records["Medication Administration Log"] = plans
	plan_names = [row["name"] for row in plans]
	records["Medication Plan Item"] = _get_child_rows(
		"Medication Plan Item", "Medication Administration Log", plan_names
	)
	events = _get_rows(
		"Medication Administration Event",
		{"participant": participant, **_date_range_filter("actual_datetime", date_filters)},
	)
	records["Medication Administration Event"] = events
	event_names = [row["name"] for row in events]
	records["Medication Event Addendum"] = _get_rows(
		"Medication Event Addendum",
		{"participant": participant, "medication_event": ["in", event_names or ["__none__"]]},
	)
	records["Medication PRN Effectiveness Review"] = _get_rows(
		"Medication PRN Effectiveness Review",
		{"participant": participant, "medication_event": ["in", event_names or ["__none__"]]},
	)
	records["Controlled Medication Transaction"] = _get_rows(
		"Controlled Medication Transaction",
		{"participant": participant, **_date_range_filter("posting_datetime", date_filters)},
	)
	drug_counts, drug_count_entries = _collect_child_dated_family(
		"Participant Drug Count",
		"Drug Count Entry",
		"drug_count_entries",
		participant,
		date_filters,
	)
	records["Participant Drug Count"] = drug_counts
	records["Drug Count Entry"] = drug_count_entries
	shift_checks, shift_check_entries = _collect_child_dated_family(
		"Shift Medication Check",
		"Shift Medication Check Entry",
		"check_entries",
		participant,
		date_filters,
	)
	records["Shift Medication Check"] = shift_checks
	records["Shift Medication Check Entry"] = shift_check_entries
	disposals, disposal_items = _collect_child_dated_family(
		"Discarded Medication Register",
		"Discarded Medication Item",
		"discarded_items",
		participant,
		date_filters,
	)
	records["Discarded Medication Register"] = disposals
	records["Discarded Medication Item"] = disposal_items
	_include_referenced_medication_plans(participant, records)
	records["Incident"] = _collect_medication_incidents(participant, records)
	for doctype in records:
		records[doctype] = _sort_records(records[doctype])
	return records


def _collect_child_dated_family(parent_doctype, child_doctype, parentfield, participant, date_filters):
	candidate_parents = _get_rows(parent_doctype, {"participant": participant})
	if not date_filters.get("from_date") and not date_filters.get("to_date"):
		selected_parents = candidate_parents
	else:
		candidate_names = [row["name"] for row in candidate_parents]
		matching_children = _get_rows(
			child_doctype,
			{
				"parenttype": parent_doctype,
				"parentfield": parentfield,
				"parent": ["in", candidate_names or ["__none__"]],
				**_date_range_filter("date", date_filters),
			},
		)
		selected_names = {row["parent"] for row in matching_children}
		selected_parents = [row for row in candidate_parents if row["name"] in selected_names]
	children = _get_child_rows(child_doctype, parent_doctype, [row["name"] for row in selected_parents])
	return selected_parents, children


def _include_referenced_medication_plans(participant, records):
	plan_names = set()
	item_names = set()
	expected_item_parents = {}
	for rows in records.values():
		for row in rows:
			plan_name = row.get("medication_plan")
			item_name = row.get("medication_plan_item")
			if plan_name:
				plan_names.add(plan_name)
			if item_name:
				item_names.add(item_name)
				if plan_name:
					expected_item_parents[item_name] = plan_name

	referenced_items = _get_rows(
		"Medication Plan Item",
		{"name": ["in", sorted(item_names) or ["__none__"]]},
	)
	items_by_name = {row["name"]: row for row in referenced_items}
	if item_names != set(items_by_name):
		frappe.throw("Audit export references a missing medication plan item.", frappe.ValidationError)
	for item_name, row in items_by_name.items():
		plan_names.add(row["parent"])
		if expected_item_parents.get(item_name) and expected_item_parents[item_name] != row["parent"]:
			frappe.throw("Audit export medication plan references are inconsistent.", frappe.ValidationError)

	referenced_plans = _get_rows(
		"Medication Administration Log",
		{"name": ["in", sorted(plan_names) or ["__none__"]]},
	)
	plans_by_name = {row["name"]: row for row in referenced_plans}
	if plan_names != set(plans_by_name):
		frappe.throw(
			"Audit export references a missing medication administration plan.", frappe.ValidationError
		)
	if any(row.get("participant") != participant for row in referenced_plans):
		frappe.throw(
			"Audit export references medication evidence for another participant.", frappe.ValidationError
		)

	all_plan_items = _get_child_rows(
		"Medication Plan Item",
		"Medication Administration Log",
		sorted(plan_names),
	)
	records["Medication Administration Log"] = _merge_records(
		records["Medication Administration Log"], referenced_plans
	)
	records["Medication Plan Item"] = _merge_records(records["Medication Plan Item"], all_plan_items)


def _merge_records(existing, additional):
	by_name = {row["name"]: row for row in existing}
	by_name.update({row["name"]: row for row in additional})
	return list(by_name.values())


def _collect_medication_incidents(participant, records):
	incident_names = set()
	for doctype in (
		"Medication Administration Event",
		"Medication PRN Effectiveness Review",
		"Controlled Medication Transaction",
	):
		for row in records.get(doctype, []):
			if row.get("incident"):
				incident_names.add(row["incident"])
	for row in records.get("Participant Drug Count", []):
		if row.get("discrepancy_incident"):
			incident_names.add(row["discrepancy_incident"])
	for row in records.get("Drug Count Entry", []):
		if row.get("discrepancy_incident"):
			incident_names.add(row["discrepancy_incident"])
	for row in records.get("Discarded Medication Item", []):
		if row.get("discrepancy_incident"):
			incident_names.add(row["discrepancy_incident"])
	if not incident_names:
		return []
	rows = _get_rows("Incident", {"participant": participant, "name": ["in", sorted(incident_names)]})
	return rows


def _collect_retained_attachment_inventory(records):
	targets = set()
	for doctype in permissions.RETAINED_EVIDENCE_DOCTYPES:
		for row in records.get(doctype, []):
			targets.add((doctype, row["name"]))
	attachments = []
	for doctype, name in sorted(targets):
		rows = frappe.get_all(
			"File",
			filters={
				"attached_to_doctype": doctype,
				"attached_to_name": name,
			},
			fields=MEDICATION_RECORD_ALLOWLISTS["File"],
			order_by="name asc",
		)
		for row in rows:
			if len(attachments) >= MAX_EXPORT_ATTACHMENTS:
				frappe.throw(
					"Audit export attachment scope exceeds the safe limit. Narrow the export filters.",
					frappe.ValidationError,
				)
			item = _validated_attachment(row)
			attachments.append(item)
	return _sort_records(attachments)


def _collect_version_metadata(records):
	version_rows = []
	for doctype, rows in records.items():
		if doctype in {"File", "Version"}:
			continue
		for row in rows:
			version_rows.extend(
				_get_rows(
					"Version",
					{"ref_doctype": doctype, "docname": row["name"]},
					limit=50,
				)
			)
			if len(version_rows) > MAX_EXPORT_VERSIONS:
				frappe.throw(
					"Audit export Version scope exceeds the safe limit. Narrow the export filters.",
					frappe.ValidationError,
				)
	return _sort_records(version_rows)


def _get_rows(doctype, filters, limit=MAX_EXPORT_RECORDS_PER_DOCTYPE):
	if not frappe.db.table_exists(doctype):
		return []
	rows = frappe.get_all(
		doctype,
		filters=filters,
		fields=MEDICATION_RECORD_ALLOWLISTS[doctype],
		order_by="modified asc, name asc" if frappe.db.has_column(doctype, "modified") else "name asc",
		limit=limit + 1,
	)
	if len(rows) > limit:
		frappe.throw(
			f"Audit export scope for {doctype} exceeds the safe limit. Narrow the export filters.",
			frappe.ValidationError,
		)
	return [_clean_row(row) for row in rows]


def _get_child_rows(doctype, parenttype, parents):
	if not parents or not frappe.db.table_exists(doctype):
		return []
	return _get_rows(
		doctype,
		{
			"parenttype": parenttype,
			"parent": ["in", parents],
		},
	)


def _clean_row(row):
	clean = {}
	for key, value in dict(row).items():
		if isinstance(value, (datetime, date)):
			clean[key] = value.isoformat()
		else:
			clean[key] = value
	return clean


def _sort_records(rows):
	return sorted(
		rows,
		key=lambda row: (
			str(row.get("attached_to_doctype") or ""),
			str(row.get("parent") or ""),
			row["name"],
		),
	)


def _validated_attachment(row):
	if not bool(row.is_private):
		frappe.throw(
			"Audit export cannot include public retained-evidence attachments.", frappe.ValidationError
		)
	path = get_file_path(row.name)
	sha256 = hashlib.sha256()
	content = bytearray()
	try:
		with open(path, "rb") as handle:
			for chunk in iter(lambda: handle.read(1024 * 1024), b""):
				sha256.update(chunk)
				content.extend(chunk)
	except (FileNotFoundError, OSError, TypeError):
		frappe.throw("Audit export retained-evidence attachment bytes are missing.", frappe.ValidationError)
	actual_size = len(content)
	actual_content_hash = get_content_hash(bytes(content))
	if row.file_size is None or int(row.file_size) != actual_size:
		frappe.throw("Audit export attachment size does not match the stored bytes.", frappe.ValidationError)
	if not row.content_hash or row.content_hash != actual_content_hash:
		frappe.throw(
			"Audit export attachment content hash does not match the stored bytes.", frappe.ValidationError
		)
	item = _clean_row(row)
	item["sha256"] = sha256.hexdigest()
	return item


def _build_manifest(participant, user, date_filters, records, attachments, versions, member_integrity):
	record_counts = {doctype: len(rows) for doctype, rows in sorted(records.items())}
	record_identities = {doctype: [row["name"] for row in rows] for doctype, rows in sorted(records.items())}
	return {
		"schema_version": EXPORT_SCHEMA_VERSION,
		"participant": participant,
		"applied_filters": {
			"from_date": date_filters["from_date"].isoformat() if date_filters.get("from_date") else None,
			"to_date": date_filters["to_date"].isoformat() if date_filters.get("to_date") else None,
		},
		"requesting_user": user,
		"generated_at": now_datetime().isoformat(),
		"date_scope_rule": CHILD_DATE_SCOPE_RULE,
		"record_counts": record_counts,
		"record_identities": record_identities,
		"attachment_identities": [
			{
				"name": row["name"],
				"attached_to_doctype": row["attached_to_doctype"],
				"attached_to_name": row["attached_to_name"],
				"file_size": row.get("file_size"),
				"sha256": row.get("sha256"),
			}
			for row in attachments
		],
		"version_identities": [row["name"] for row in versions],
		"members": member_integrity,
	}


def _zip_payload(members):
	output = io.BytesIO()
	with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
		for name, content in members.items():
			_safe_member_name(name)
			bundle.writestr(name, content)
	return output.getvalue()


def verify_bundle_content(manifest, members):
	for name in ("records.json", "attachments.json", "versions.json"):
		content = members.get(name)
		expected = manifest.get("members", {}).get(name)
		if not isinstance(content, bytes) or not expected:
			frappe.throw("Audit bundle content manifest is incomplete.", frappe.ValidationError)
		if (
			expected.get("bytes") != len(content)
			or expected.get("sha256") != hashlib.sha256(content).hexdigest()
		):
			frappe.throw(f"Audit bundle content integrity failed for {name}.", frappe.ValidationError)
	if manifest.get("bundle_manifest_hash") != _manifest_hash(manifest):
		frappe.throw("Audit bundle manifest integrity verification failed.", frappe.ValidationError)
	return True


def _manifest_hash(manifest):
	canonical = dict(manifest)
	canonical.pop("bundle_manifest_hash", None)
	return hashlib.sha256(_json_bytes(canonical)).hexdigest()


def _enforce_bundle_size(members):
	total_bytes = sum(len(content) for content in members.values())
	if total_bytes > MAX_EXPORT_UNCOMPRESSED_BYTES:
		frappe.throw(
			"Audit export serialized content exceeds the safe byte limit. Narrow the export filters.",
			frappe.ValidationError,
		)


def _safe_member_name(name):
	normalized = posixpath.normpath(str(name or ""))
	if normalized.startswith("../") or normalized.startswith("/") or normalized in {"", "."}:
		frappe.throw("Unsafe audit bundle member path.", frappe.ValidationError)
	if normalized != name:
		frappe.throw("Unsafe audit bundle member path.", frappe.ValidationError)
	return normalized


def _safe_filename(name):
	return "".join(char if char.isalnum() or char in {"-", "_", "."} else "-" for char in name)[:140]


def _json_dumps(value):
	return json.dumps(value, sort_keys=True, indent=2, default=str)


def _json_bytes(value):
	return _json_dumps(value).encode("utf-8")
