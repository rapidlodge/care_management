# Copyright (c) 2026, Care Management and contributors
# For license information, please see license.txt

import hashlib
from decimal import Decimal, InvalidOperation

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from care_management.care_management import permissions
from care_management.care_management.doctype.medication_competency.medication_competency import (
	has_active_medication_competency,
)

INCREASE_TYPES = frozenset({"Opening Balance", "Receipt", "Correction Increase"})
DECREASE_TYPES = frozenset({"Administration", "Disposal", "Return to Pharmacy", "Correction Decrease"})
SOURCE_GENERATED_TYPES = frozenset({"Administration", "Disposal", "Return to Pharmacy"})


@frappe.whitelist()
def search_controlled_transaction_participants(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_controlled_transaction_participants(
		doctype, txt, searchfield, start, page_len, filters=filters
	)


@frappe.whitelist()
def search_controlled_transaction_plans(doctype, txt, searchfield, start, page_len, filters=None):
	return permissions.search_controlled_transaction_plans(doctype, txt, searchfield, start, page_len, filters=filters)


def canonical_decimal(value):
	try:
		amount = Decimal(str(value))
	except (InvalidOperation, TypeError, ValueError):
		frappe.throw("Medication quantity must be a canonical number.", frappe.ValidationError)
	if amount <= 0:
		frappe.throw("Medication quantity must be positive.", frappe.ValidationError)
	return amount


def source_key(source_doctype, source_docname, source_action):
	source = f"{source_doctype}|{source_docname}|{source_action}"
	return hashlib.sha256(source.encode("utf-8")).hexdigest()


def latest_balance(participant, medication_plan_item):
	row = frappe.get_all(
		"Controlled Medication Transaction",
		filters={
			"participant": participant,
			"medication_plan_item": medication_plan_item,
			"docstatus": 1,
		},
		fields=["balance_after"],
		order_by="finalized_on desc, modified desc, name desc",
		limit=1,
	)
	return Decimal(str(row[0].balance_after)) if row else Decimal("0")


def lock_plan_item_row(medication_plan_item):
	if not medication_plan_item:
		frappe.throw("Medication plan item is required for controlled medication accounting.", frappe.ValidationError)
	frappe.db.sql(
		"select name from `tabMedication Plan Item` where name = %s for update",
		(medication_plan_item,),
	)


def create_source_transaction(source_doc, transaction_type, quantity, witness, reason=None, incident=None, actor=None):
	participant = source_doc.participant
	plan_item = source_doc.medication_plan_item
	source_action = source_doc.get("source_action") or transaction_type
	lock_plan_item_row(plan_item)
	amount = canonical_decimal(quantity)
	operational_actor = permissions.normalize_user(
		actor or source_doc.get("worker") or source_doc.get("operational_actor") or permissions.normalize_user()
	)
	source_context = {
		"source_doctype": source_doc.doctype,
		"source_docname": source_doc.name,
		"source_action": source_action,
		"actor": operational_actor,
	}
	with permissions.controlled_transaction_source_context(source_context):
		txn = frappe.get_doc(
			{
				"doctype": "Controlled Medication Transaction",
				"participant": participant,
				"medication_plan": source_doc.medication_plan,
				"medication_plan_item": plan_item,
				"posting_datetime": source_doc.actual_datetime or now_datetime(),
				"transaction_type": transaction_type,
				"quantity": str(amount),
				"dose_unit": source_doc.dose_unit,
				"actor": operational_actor,
				"witness": witness,
				"source_doctype": source_doc.doctype,
				"source_docname": source_doc.name,
				"source_action": source_action,
				"source_key": source_key(source_doc.doctype, source_doc.name, source_action),
				"reason": reason,
				"incident": incident,
			}
		)
		txn.insert()
		txn.submit()
	return txn


def direction_for_type(transaction_type):
	if transaction_type in INCREASE_TYPES:
		return "Increase"
	if transaction_type in DECREASE_TYPES:
		return "Decrease"
	frappe.throw("Controlled medication transaction type is not supported.", frappe.ValidationError)


class ControlledMedicationTransaction(Document):
	def before_insert(self):
		self._derive_authoritative_evidence()

	def validate(self):
		self._derive_authoritative_evidence()
		self._validate_source_authority()
		self._validate_required_context()
		self._validate_witness()
		self._validate_balance()
		self.source_key = source_key(self.source_doctype, self.source_docname, self.source_action)

	def before_submit(self):
		self._derive_authoritative_evidence()
		self._validate_source_authority()
		self._validate_required_context()
		self._validate_witness()
		self._validate_balance()
		self.finalized_by = permissions.normalize_user()
		self.finalized_on = now_datetime()

	def before_update_after_submit(self):
		frappe.throw("Submitted controlled medication transactions cannot be edited.", frappe.ValidationError)

	def before_cancel(self):
		frappe.throw("Submitted controlled medication transactions cannot be cancelled.", frappe.ValidationError)

	def on_trash(self):
		if self.docstatus == 1:
			frappe.throw("Submitted controlled medication transactions cannot be deleted.", frappe.ValidationError)

	def _validate_source_authority(self):
		context = permissions.get_controlled_transaction_source_context()
		if self.transaction_type in SOURCE_GENERATED_TYPES:
			if not context:
				frappe.throw("Source-generated controlled transactions cannot be fabricated directly.", frappe.PermissionError)
			for fieldname in ("source_doctype", "source_docname", "source_action"):
				if self.get(fieldname) != context.get(fieldname):
					frappe.throw("Controlled transaction provenance does not match the trusted source context.", frappe.PermissionError)
			actor = permissions.normalize_user(context.get("actor"))
			if not actor or self.actor != actor:
				frappe.throw("Controlled transaction actor does not match the trusted source context.", frappe.PermissionError)
			if not permissions.is_enabled_system_user(actor):
				raise frappe.PermissionError
			if not permissions.has_any_role({"Support Worker", "Care Manager", "System Manager"}, user=actor):
				raise frappe.PermissionError
			if actor != "Administrator" and not permissions.has_participant_access(
				self.participant,
				user=actor,
				administrative=permissions.is_system_manager(actor),
				applicable_for=context.get("source_doctype"),
			):
				raise frappe.PermissionError
			if permissions.has_any_role({"Support Worker"}, user=actor) and not has_active_medication_competency(
				actor, "Controlled Medication", get_datetime(self.posting_datetime).date()
			):
				raise frappe.PermissionError
		if self.transaction_type == "Opening Balance":
			if self._has_prior_submitted_transaction():
				frappe.throw("Opening Balance is allowed only before prior transactions exist.", frappe.ValidationError)
			permissions.require_any_role({"System Manager", "Care Manager"})
		if self.transaction_type in {"Correction Increase", "Correction Decrease"}:
			if not self.reason or not self.incident or not self.reverses_transaction:
				frappe.throw("Controlled medication corrections require reason, incident and reversed transaction.", frappe.ValidationError)
			self._validate_correction_reference()

	def _derive_authoritative_evidence(self):
		if not self.transaction_type:
			frappe.throw("Controlled medication transaction type is required.", frappe.ValidationError)
		self.direction = direction_for_type(self.transaction_type)
		context = permissions.get_controlled_transaction_source_context()
		self.actor = permissions.normalize_user(context.get("actor")) if context else permissions.normalize_user()
		if not self.posting_datetime:
			self.posting_datetime = now_datetime()
		if self.transaction_type in SOURCE_GENERATED_TYPES and context:
			for fieldname in ("source_doctype", "source_docname", "source_action"):
				if self.get(fieldname) and self.get(fieldname) != context.get(fieldname):
					frappe.throw("Controlled transaction provenance does not match the trusted source context.", frappe.PermissionError)
			self.source_doctype = context.get("source_doctype")
			self.source_docname = context.get("source_docname")
			self.source_action = context.get("source_action")
		elif self.transaction_type not in SOURCE_GENERATED_TYPES:
			self.source_doctype = self.doctype
			self.source_docname = self.name
			self.source_action = self.transaction_type
		lock_plan_item_row(self.medication_plan_item)
		quantity = canonical_decimal(self.quantity)
		before = latest_balance(self.participant, self.medication_plan_item)
		after = before + quantity if self.direction == "Increase" else before - quantity
		self.balance_before = str(before)
		self.balance_after = str(after)
		self.source_key = source_key(self.source_doctype, self.source_docname, self.source_action)

	def _validate_correction_reference(self):
		reversed_txn = frappe.db.get_value(
			self.doctype,
			self.reverses_transaction,
			[
				"name",
				"docstatus",
				"participant",
				"medication_plan",
				"medication_plan_item",
				"dose_unit",
				"direction",
				"quantity",
			],
			as_dict=True,
		)
		if not reversed_txn or reversed_txn.docstatus != 1:
			frappe.throw("Controlled medication correction must reverse a submitted transaction.", frappe.ValidationError)
		if (
			reversed_txn.participant != self.participant
			or reversed_txn.medication_plan != self.medication_plan
			or reversed_txn.medication_plan_item != self.medication_plan_item
			or reversed_txn.dose_unit != self.dose_unit
		):
			raise frappe.PermissionError
		if reversed_txn.direction == self.direction:
			frappe.throw("Controlled medication correction direction must offset the referenced transaction.", frappe.ValidationError)
		if canonical_decimal(reversed_txn.quantity) != canonical_decimal(self.quantity):
			frappe.throw("Controlled medication correction quantity must exactly offset the referenced transaction.", frappe.ValidationError)
		existing_reversal = frappe.db.exists(
			self.doctype,
			{
				"reverses_transaction": self.reverses_transaction,
				"docstatus": ["!=", 2],
				"name": ["!=", self.name],
			},
		)
		if existing_reversal:
			frappe.throw("Controlled medication transaction has already been reversed.", frappe.ValidationError)

	def _has_prior_submitted_transaction(self):
		filters = {
			"participant": self.participant,
			"medication_plan_item": self.medication_plan_item,
			"docstatus": 1,
		}
		if self.name:
			filters["name"] = ["!=", self.name]
		return bool(frappe.db.exists("Controlled Medication Transaction", filters))

	def _validate_required_context(self):
		plan = frappe.get_doc("Medication Administration Log", self.medication_plan)
		if plan.participant != self.participant:
			frappe.throw("Controlled transaction participant must match the medication plan.", frappe.PermissionError)
		item = None
		for row in plan.medication_items:
			if row.name == self.medication_plan_item:
				item = row
				break
		if not item or not item.get("is_controlled_drug"):
			frappe.throw("Controlled transaction requires a controlled medication plan item.", frappe.ValidationError)
		if self.dose_unit != item.dose_unit:
			frappe.throw("Controlled transaction dose unit must match the medication plan item.", frappe.ValidationError)
		if self.incident and permissions.resolve_participant("Incident", self.incident) != self.participant:
			raise frappe.PermissionError

	def _validate_witness(self):
		actor = permissions.normalize_user(self.actor)
		witness = permissions.normalize_user(self.witness)
		if not actor or not witness or actor == witness:
			raise frappe.PermissionError
		if not permissions.is_enabled_system_user(witness):
			raise frappe.PermissionError
		if not permissions.has_any_role({"Support Worker", "Care Manager", "System Manager"}, user=witness):
			raise frappe.PermissionError
		if witness != "Administrator" and not permissions.has_participant_access(
			self.participant, user=witness, administrative=permissions.is_system_manager(witness), applicable_for=self.doctype
		):
			raise frappe.PermissionError
		if permissions.has_any_role({"Support Worker"}, user=witness) and not has_active_medication_competency(
			witness, "Controlled Medication", get_datetime(self.posting_datetime).date()
		):
			raise frappe.PermissionError

	def _validate_balance(self):
		quantity = canonical_decimal(self.quantity)
		before = Decimal(str(self.balance_before or 0))
		after = Decimal(str(self.balance_after or 0))
		if self.direction != direction_for_type(self.transaction_type):
			frappe.throw("Controlled transaction direction does not match its type.", frappe.ValidationError)
		expected = before + quantity if self.direction == "Increase" else before - quantity
		if expected != after or after < 0:
			frappe.throw("Controlled medication balance is invalid.", frappe.ValidationError)
