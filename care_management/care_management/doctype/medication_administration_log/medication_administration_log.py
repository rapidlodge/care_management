# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

from frappe.model.document import Document
import frappe
from frappe.utils import get_datetime, getdate, now_datetime

from care_management.care_management import permissions
from care_management.care_management.doctype.medication_plan_item.medication_plan_item import (
	PROTECTED_HISTORY_FIELDS,
	WEEKDAY_FIELDS,
	history_values_match,
	validate_active_medication_plan_items,
)


_AUTHORITATIVE_SUPERSESSION_DOCUMENTS = set()
VALID_PLAN_STATUSES = frozenset({"Needs Review", "Draft", "Active", "Superseded", "Archived"})


def _log_history_value(fieldname, value):
	if value in (None, ""):
		return None
	field = frappe.get_meta("Medication Administration Log").get_field(fieldname)
	fieldtype = field.fieldtype if field else None
	try:
		if fieldtype == "Date":
			return getdate(value)
		if fieldtype == "Datetime":
			return get_datetime(value)
		if fieldtype in {"Check", "Int"}:
			return int(value)
	except Exception:
		return object()
	return value


def _log_history_values_match(fieldname, left, right):
	return _log_history_value(fieldname, left) == _log_history_value(fieldname, right)


class MedicationAdministrationLog(Document):
	def before_insert(self):
		if not self.plan_status:
			self.plan_status = "Needs Review"
		if not self.plan_version:
			self.plan_version = 1

	def validate(self):
		self._validate_participant_unchanged()
		self._validate_initial_status()
		self._validate_replacement_provenance()
		self._validate_lifecycle_transition()
		self._validate_locked_metadata_unchanged()
		self._validate_dates()
		self._validate_historical_items_unchanged()
		self._validate_incoming_item_moves_preserve_source_collections()
		if self.plan_status == "Active":
			self._validate_activation_requirements()
			self._validate_no_active_overlap()
		if self._is_activation_transition():
			self._supersede_previous_plan()

	def on_trash(self):
		if self.plan_status in {"Active", "Superseded", "Archived"}:
			frappe.throw("Locked medication plans cannot be deleted.", frappe.ValidationError)

	def _previous(self, fields):
		if self.is_new():
			return None
		return frappe.db.get_value(self.doctype, self.name, fields, as_dict=True)

	def _is_activation_transition(self):
		previous = self._previous(["plan_status"])
		return bool(previous and previous.plan_status == "Draft" and self.plan_status == "Active")

	def _is_authoritative_supersession(self):
		return id(self) in _AUTHORITATIVE_SUPERSESSION_DOCUMENTS

	def _validate_initial_status(self):
		if not self.is_new():
			if not self.plan_status or self.plan_status not in VALID_PLAN_STATUSES:
				frappe.throw("Medication plan status is not supported.", frappe.ValidationError)
			return
		if self.plan_status not in {"Needs Review", "Draft"}:
			frappe.throw("New medication plans must start in Draft or Needs Review.", frappe.ValidationError)

	def _validate_participant_unchanged(self):
		previous = self._previous(["participant"])
		if previous and previous.participant != self.participant:
			frappe.throw("Participant cannot be changed after save.", frappe.ValidationError)

	def _validate_replacement_provenance(self):
		if self.is_new():
			if self.replacement_plan:
				frappe.throw("Medication plan replacement relationship cannot be caller-controlled.", frappe.ValidationError)
			return
		previous = self._previous(["plan_status", "replacement_plan"])
		if previous and previous.plan_status in {"Needs Review", "Draft"} and self.replacement_plan:
			frappe.throw("Medication plan replacement relationship cannot be caller-controlled.", frappe.ValidationError)

	def _validate_lifecycle_transition(self):
		if self.is_new():
			return
		previous = self._previous(["plan_status"])
		old_status = previous.plan_status if previous else None
		new_status = self.plan_status
		if old_status == new_status:
			return
		if old_status == "Active" and new_status == "Superseded":
			if self._is_authoritative_supersession():
				return
			frappe.throw("Active medication plans can only be superseded by an approved replacement plan.", frappe.ValidationError)
		allowed = {
			("Needs Review", "Draft"),
			("Draft", "Active"),
			("Superseded", "Archived"),
		}
		if old_status == "Active" and new_status == "Archived" and self.lifecycle_reason:
			return
		if (old_status, new_status) not in allowed:
			frappe.throw(f"Medication plan transition {old_status} to {new_status} is not allowed.", frappe.ValidationError)

	def _validate_locked_metadata_unchanged(self):
		previous = self._previous(
			[
				"plan_status",
				"plan_version",
				"previous_plan",
				"approved_by",
				"approved_on",
				"effective_from",
				"effective_to",
				"replacement_plan",
			]
		)
		if not previous or previous.plan_status not in {"Active", "Superseded", "Archived"}:
			return
		transitioning_to = self.plan_status or previous.plan_status
		for fieldname in ("plan_version", "previous_plan", "approved_by", "approved_on"):
			if not _log_history_values_match(fieldname, previous.get(fieldname), self.get(fieldname)):
				frappe.throw("Locked medication plan approval and version metadata cannot be changed.", frappe.ValidationError)
		replacement_changed = not _log_history_values_match(
			"replacement_plan", previous.get("replacement_plan"), self.get("replacement_plan")
		)
		is_authoritative_supersession = bool(
			previous.plan_status == "Active"
			and transitioning_to == "Superseded"
			and self._is_authoritative_supersession()
		)
		if replacement_changed and not is_authoritative_supersession:
			frappe.throw("Medication plan replacement relationship cannot be changed directly.", frappe.ValidationError)
		if (
			frappe.db.table_exists("Medication Administration Event")
			and frappe.db.exists("Medication Administration Event", {"medication_plan": self.name})
		):
			for fieldname in ("effective_from", "effective_to"):
				if not _log_history_values_match(fieldname, previous.get(fieldname), self.get(fieldname)):
					frappe.throw("Event-bound medication plan effective periods cannot be changed.", frappe.ValidationError)
		if previous.plan_status == "Active" and transitioning_to not in {"Active", "Superseded", "Archived"}:
			frappe.throw("Active medication plans can only be superseded or archived.", frappe.ValidationError)

	def _validate_dates(self):
		if self.effective_from and self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw("Medication plan effective end date cannot be before its start date.", frappe.ValidationError)
		if self.effective_from and self.review_date and getdate(self.review_date) < getdate(self.effective_from):
			frappe.throw("Medication plan review date cannot be before its start date.", frappe.ValidationError)

	def _validate_activation_requirements(self):
		is_activation = self._is_activation_transition()
		actor = permissions.normalize_user()
		if is_activation:
			if not actor:
				raise frappe.PermissionError
			if actor not in {"Administrator"} and not permissions.has_any_role({"System Manager", "Care Manager"}, user=actor):
				raise frappe.PermissionError
			if (
				actor != "Administrator"
				and not permissions.has_any_role({"System Manager"}, user=actor)
				and permissions.has_any_role({"Care Manager"}, user=actor)
				and not permissions.has_participant_access(
				self.participant,
				user=actor,
				applicable_for="Medication Administration Log",
				)
			):
				raise frappe.PermissionError
		if not self.effective_from:
			frappe.throw("Active medication plans require an effective start date.", frappe.ValidationError)
		if not self.review_date:
			frappe.throw("Active medication plans require a review date.", frappe.ValidationError)
		if self.purpose_evidence_status != "Recorded":
			frappe.throw("Medication purpose evidence must be recorded before activation.", frappe.ValidationError)
		_validate_r3c2_medication_safeguard_activation(self.medication_items)
		if self.previous_plan:
			previous = frappe.get_doc("Medication Administration Log", self.previous_plan)
			if is_activation and (previous.participant != self.participant or previous.plan_status != "Active"):
				frappe.throw("Replacement plans must supersede an active plan for the same participant.", frappe.ValidationError)
			if not is_activation:
				if previous.participant != self.participant or previous.plan_status not in {"Superseded", "Archived"}:
					frappe.throw("Active replacement plans must retain their superseded predecessor.", frappe.ValidationError)
				if previous.replacement_plan != self.name:
					frappe.throw("Active replacement plans must retain the authoritative replacement relationship.", frappe.ValidationError)
			if self.plan_version != (previous.plan_version or 0) + 1:
				frappe.throw("Replacement plan version must follow the previous active plan.", frappe.ValidationError)
		if is_activation:
			self.approved_by = actor
			self.approved_on = now_datetime()

	def _supersede_previous_plan(self):
		if not self.previous_plan:
			return
		previous = frappe.get_doc("Medication Administration Log", self.previous_plan)
		if previous.name == self.name:
			frappe.throw("A medication plan cannot replace itself.", frappe.ValidationError)
		if previous.participant != self.participant or previous.plan_status != "Active":
			frappe.throw("Replacement plans must supersede an active plan for the same participant.", frappe.ValidationError)
		previous.plan_status = "Superseded"
		previous.replacement_plan = self.name
		if not previous.lifecycle_reason:
			previous.lifecycle_reason = self.change_reason or "Superseded by replacement plan"
		_AUTHORITATIVE_SUPERSESSION_DOCUMENTS.add(id(previous))
		try:
			previous.save()
		finally:
			_AUTHORITATIVE_SUPERSESSION_DOCUMENTS.discard(id(previous))

	def _validate_no_active_overlap(self):
		start = getdate(self.effective_from)
		end = getdate(self.effective_to) if self.effective_to else getdate("9999-12-31")
		for row in frappe.get_all(
			"Medication Administration Log",
			filters={"participant": self.participant, "plan_status": "Active"},
			fields=["name", "effective_from", "effective_to"],
		):
			if row.name == self.name or row.name == self.previous_plan:
				continue
			other_start = getdate(row.effective_from) if row.effective_from else getdate("0001-01-01")
			other_end = getdate(row.effective_to) if row.effective_to else getdate("9999-12-31")
			if start <= other_end and other_start <= end:
				frappe.throw("Overlapping active medication plans are not allowed.", frappe.ValidationError)

	def _validate_historical_items_unchanged(self):
		if self.is_new() or not frappe.db.table_exists("Medication Administration Event"):
			return
		persisted = frappe.get_doc("Medication Administration Log", self.name)
		current_rows = {row.name: row for row in self.medication_items if row.name}
		persisted_rows = {row.name: row for row in persisted.medication_items if row.name}
		for row_name, old in persisted_rows.items():
			if not frappe.db.exists("Medication Administration Event", {"medication_plan_item": row_name}):
				continue
			row = current_rows.get(row_name)
			if not row:
				frappe.throw("Referenced medication plan items cannot be removed or replaced.", frappe.ValidationError)
			if row.parent != self.name or row.parenttype != self.doctype or row.parentfield != "medication_items":
				frappe.throw("Referenced medication plan items cannot be reparented.", frappe.ValidationError)
			for fieldname in PROTECTED_HISTORY_FIELDS:
				if not history_values_match(fieldname, old.get(fieldname), row.get(fieldname)):
					frappe.throw("Referenced medication plan items cannot be materially changed.", frappe.ValidationError)
		for row_name in current_rows:
			if row_name in persisted_rows:
				continue
			if frappe.db.exists("Medication Administration Event", {"medication_plan_item": row_name}):
				frappe.throw("Referenced medication plan items cannot be moved between medication plans.", frappe.ValidationError)

	def _validate_incoming_item_moves_preserve_source_collections(self):
		if self.is_new():
			return
		current_rows = [row for row in self.medication_items if row.name]
		for row in current_rows:
			if not frappe.db.exists("Medication Plan Item", row.name):
				continue
			stored = frappe.get_doc("Medication Plan Item", row.name)
			if not _row_belongs_to_medication_plan(stored):
				continue
			if stored.parent == self.name:
				continue
			_validate_source_collection_after_item_move(stored.parent, stored.name, destination_plan=self.name)



def _validate_r3c2_medication_safeguard_activation(rows):
	validate_active_medication_plan_items(rows)


_WEEKDAY_FIELDS = WEEKDAY_FIELDS


def _row_belongs_to_medication_plan(row):
	return (
		row.get("parent")
		and row.get("parenttype") == "Medication Administration Log"
		and row.get("parentfield") == "medication_items"
	)


def _validate_source_collection_after_item_move(source_plan, moved_item_name, destination_plan=None):
	if not source_plan or not frappe.db.exists("Medication Administration Log", source_plan):
		return
	if not destination_plan or not frappe.db.exists("Medication Administration Log", destination_plan):
		frappe.throw("Medication plan items can only be moved into a stored medication plan.", frappe.ValidationError)
	source_participant = frappe.db.get_value("Medication Administration Log", source_plan, "participant")
	destination_participant = frappe.db.get_value("Medication Administration Log", destination_plan, "participant")
	if source_participant != destination_participant:
		frappe.throw("Medication plan items cannot move across participants.", frappe.ValidationError)
	if frappe.db.get_value("Medication Administration Log", source_plan, "plan_status") != "Active":
		return
	fields = sorted({"name", *PROTECTED_HISTORY_FIELDS})
	rows = frappe.get_all(
		"Medication Plan Item",
		filters={
			"parent": source_plan,
			"parenttype": "Medication Administration Log",
			"parentfield": "medication_items",
		},
		fields=fields,
		order_by="idx asc, name asc",
	)
	validate_active_medication_plan_items([frappe._dict(row) for row in rows if row.name != moved_item_name])
