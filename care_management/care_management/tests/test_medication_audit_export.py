import hashlib
import inspect
import io
import json
import os
import zipfile
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate
from frappe.utils.file_manager import get_file_path

from care_management.care_management import audit_export
from care_management.care_management.tests.helpers import (
	ensure_r2c1_participant,
	ensure_r2c1_support_plan,
	ensure_r2c1_task_assignment,
	ensure_r2c1_user,
	ensure_r2c1_user_permission,
)


class TestMedicationAuditExport(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.participant_a = ensure_r2c1_participant("R3G A", "5234567890")
		self.participant_b = ensure_r2c1_participant("R3G B", "4234567890")
		self.worker = ensure_r2c1_user("R3G Worker", ["Support Worker"])
		self.care_manager = ensure_r2c1_user("R3G Care Manager", ["Care Manager"])
		self.ungranted_manager = ensure_r2c1_user("R3G Ungranted Manager", ["Care Manager"])
		self.system_manager = ensure_r2c1_user("R3G System Manager", ["System Manager"])
		for user, participant in (
			(self.worker, self.participant_a),
			(self.care_manager, self.participant_a),
			(self.system_manager, self.participant_a),
		):
			for doctype in (
				"Medication Administration Log",
				"Medication Administration Event",
				"Medication Event Addendum",
				"Medication Competency",
			):
				ensure_r2c1_user_permission(user, participant, applicable_for=doctype)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def _grant_competency(self):
		existing = frappe.db.get_value(
			"Medication Competency",
			{"worker": self.worker, "competency_type": "General Medication", "status": "Active"},
			"name",
		)
		if existing:
			return existing
		return (
			frappe.get_doc(
				{
					"doctype": "Medication Competency",
					"worker": self.worker,
					"competency_type": "General Medication",
					"status": "Active",
					"valid_from": nowdate(),
					"expiry_date": add_days(nowdate(), 30),
					"assessed_by": self.care_manager,
					"assessed_on": nowdate(),
				}
			)
			.insert(ignore_permissions=True)
			.name
		)

	def _active_plan_and_task(self, participant=None):
		participant = participant or self.participant_a
		plan = frappe.get_doc(
			{
				"doctype": "Medication Administration Log",
				"participant": participant,
				"week_commencing": nowdate(),
				"plan_status": "Draft",
				"plan_version": 1,
				"effective_from": nowdate(),
				"review_date": add_days(nowdate(), 30),
				"purpose_evidence_status": "Recorded",
				"change_reason": "R3G activation",
				"medication_items": [
					{
						"medication_name": "R3G Paracetamol",
						"dosage": "10 mg",
						"prescribed_dose": "10",
						"dose_unit": "mg",
						"route": "Oral",
						"time_slot": "8 AM",
						"medication_form": "Tablet",
						"strength": "10 mg",
						"frequency": "Daily",
						"scheduled_time": "08:00:00",
						"indication": "Routine support",
						"is_active": 1,
						"monday": 1,
						"tuesday": 1,
						"wednesday": 1,
						"thursday": 1,
						"friday": 1,
						"saturday": 1,
						"sunday": 1,
						"requires_competency": 1,
						"is_prn": 0,
						"is_controlled_drug": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		plan.plan_status = "Active"
		plan.save(ignore_permissions=True)
		support_plan = ensure_r2c1_support_plan(participant, f"R3G {participant}")
		task = frappe.get_doc(
			{
				"doctype": "Support Task",
				"support_plan": support_plan,
				"task_name": f"R3G Medication Task {frappe.generate_hash(length=8)}",
				"task_category": "Medication",
				"status": "Active",
				"clinical_priority": "Mandatory",
				"staff_count_required": 1,
				"source_doctype": "Medication Administration Log",
				"source_docname": plan.name,
				"source_row_id": plan.medication_items[0].name,
				"schedule_rules": [
					{
						"scheduled_time": "08:00:00",
						"recurrence_type": "Daily",
						"start_date": nowdate(),
						"is_floating": 0,
					}
				],
			}
		).insert(ignore_permissions=True)
		ensure_r2c1_task_assignment(task.name, self.worker)
		return plan, task.name

	def _submitted_event_with_addendum_and_file(self, participant=None):
		participant = participant or self.participant_a
		self._grant_competency()
		plan, task = self._active_plan_and_task(participant=participant)
		event = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": participant,
				"medication_plan": plan.name,
				"medication_plan_item": plan.medication_items[0].name,
				"support_task": task,
				"scheduled_datetime": f"{nowdate()} 08:00:00",
				"actual_datetime": f"{nowdate()} 08:01:00",
				"worker": self.worker,
				"outcome": "Administered",
				"administered_dose": "10",
			}
		)
		frappe.set_user(self.worker)
		event.insert()
		event.submit()
		addendum = frappe.get_doc(
			{
				"doctype": "Medication Event Addendum",
				"medication_event": event.name,
				"amendment_reason": "R3G audit clarification",
				"correction_explanation": "Synthetic audit export evidence.",
			}
		).insert()
		frappe.set_user(self.care_manager)
		addendum.review_decision = "Approved"
		addendum.review_comments = "R3G manager review evidence."
		addendum.submit()
		frappe.set_user("Administrator")
		file_doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"r3g-{frappe.generate_hash(length=8)}.txt",
				"content": "R3G synthetic retained audit evidence",
				"attached_to_doctype": event.doctype,
				"attached_to_name": event.name,
				"is_private": 1,
			}
		).insert(ignore_permissions=True)
		return plan, event, addendum, file_doc

	def _read_bundle(self, bundle):
		with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
			self.assertEqual(
				sorted(archive.namelist()),
				["attachments.json", "manifest.json", "records.json", "versions.json"],
			)
			for name in archive.namelist():
				self.assertFalse(name.startswith("/"))
				self.assertNotIn("..", name.split("/"))
			return {name: json.loads(archive.read(name).decode("utf-8")) for name in archive.namelist()}

	def _insert_dated_parent(self, doctype, child_doctype, child_field, participant, dates, **values):
		parent = frappe.get_doc({"doctype": doctype, "participant": participant, **values})
		parent.db_insert()
		children = []
		for index, entry_date in enumerate(dates, start=1):
			child = frappe.get_doc(
				{
					"doctype": child_doctype,
					"parent": parent.name,
					"parenttype": doctype,
					"parentfield": child_field,
					"idx": index,
					"date": entry_date,
				}
			)
			child.db_insert()
			children.append(child)
		return parent, children

	def _raw_bundle_members(self, bundle):
		with zipfile.ZipFile(io.BytesIO(bundle), "r") as archive:
			return {name: archive.read(name) for name in archive.namelist()}

	def _incident(self, participant=None):
		doc = frappe.get_doc(
			{
				"doctype": "Incident",
				"participant": participant or self.participant_a,
				"incident_status": "Open",
				"incident_type": "Medication Error",
				"date_of_incident": nowdate(),
			}
		)
		doc.db_insert()
		return doc

	def _attachment_row(self, content, **overrides):
		values = {
			"name": "synthetic-private-file",
			"file_name": "synthetic.txt",
			"attached_to_doctype": "Medication Administration Event",
			"attached_to_name": "synthetic-event",
			"is_private": 1,
			"file_size": len(content),
			"content_hash": hashlib.md5(content, usedforsecurity=False).hexdigest(),
			"creation": None,
			"owner": "Administrator",
		}
		values.update(overrides)
		return frappe._dict(values)

	def test_authorized_manager_exports_scoped_medication_audit_bundle(self):
		plan, event, addendum, file_doc = self._submitted_event_with_addendum_and_file()
		other_plan, other_task = self._active_plan_and_task(participant=self.participant_b)
		frappe.set_user("Administrator")
		other_event = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": self.participant_b,
				"medication_plan": other_plan.name,
				"medication_plan_item": other_plan.medication_items[0].name,
				"support_task": other_task,
				"scheduled_datetime": f"{nowdate()} 08:00:00",
				"actual_datetime": f"{nowdate()} 08:02:00",
				"worker": self.worker,
				"outcome": "Administered",
				"administered_dose": "10",
			}
		).insert(ignore_permissions=True)

		bundle = audit_export.build_medication_audit_bundle(
			self.participant_a,
			user=self.care_manager,
			from_date=nowdate(),
			to_date=nowdate(),
		)
		data = self._read_bundle(bundle)
		manifest = data["manifest.json"]
		records = data["records.json"]

		self.assertEqual(manifest["schema_version"], audit_export.EXPORT_SCHEMA_VERSION)
		self.assertEqual(manifest["participant"], self.participant_a)
		self.assertEqual(manifest["requesting_user"], self.care_manager)
		self.assertIn(plan.name, manifest["record_identities"]["Medication Administration Log"])
		self.assertIn(event.name, manifest["record_identities"]["Medication Administration Event"])
		self.assertIn(addendum.name, manifest["record_identities"]["Medication Event Addendum"])
		self.assertNotIn(other_event.name, manifest["record_identities"]["Medication Administration Event"])
		self.assertEqual(records["Medication Administration Event"][0]["participant"], self.participant_a)
		self.assertNotIn("notes", records["Medication Administration Event"][0])
		self.assertNotIn("full_description_of_incident", json.dumps(records))

		attachment = data["attachments.json"][0]
		self.assertEqual(attachment["name"], file_doc.name)
		with open(get_file_path(file_doc.name), "rb") as handle:
			self.assertEqual(attachment["sha256"], hashlib.sha256(handle.read()).hexdigest())
		self.assertTrue(manifest["bundle_manifest_hash"])

	def test_support_worker_ungranted_manager_and_cross_participant_are_denied(self):
		self._submitted_event_with_addendum_and_file()
		for user in (self.worker, self.ungranted_manager):
			with self.assertRaises(frappe.PermissionError):
				audit_export.build_medication_audit_bundle(self.participant_a, user=user)
		with self.assertRaises(frappe.PermissionError):
			audit_export.build_medication_audit_bundle(self.participant_b, user=self.care_manager)

	def test_system_manager_still_requires_explicit_participant_grant(self):
		self._submitted_event_with_addendum_and_file()
		self.assertTrue(
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.system_manager)
		)
		with self.assertRaises(frappe.PermissionError):
			audit_export.build_medication_audit_bundle(self.participant_b, user=self.system_manager)

	def test_invalid_filters_unknown_participant_and_empty_results_are_safe(self):
		with self.assertRaises(frappe.PermissionError):
			audit_export.build_medication_audit_bundle("missing-participant", user=self.care_manager)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(
				self.participant_a,
				user=self.care_manager,
				from_date=add_days(nowdate(), 1),
				to_date=nowdate(),
			)
		empty_participant = ensure_r2c1_participant("R3G Empty", "3234567890")
		ensure_r2c1_user_permission(
			self.care_manager, empty_participant, applicable_for="Medication Administration Log"
		)
		data = self._read_bundle(
			audit_export.build_medication_audit_bundle(empty_participant, user=self.care_manager)
		)
		self.assertEqual(sum(data["manifest.json"]["record_counts"].values()), 0)

	def test_export_scope_limit_fails_closed_instead_of_truncating(self):
		with patch("frappe.get_all", return_value=[frappe._dict(name="synthetic-overflow")]):
			with self.assertRaises(frappe.ValidationError):
				audit_export._get_rows(
					"Medication Administration Log",
					{"participant": self.participant_a},
					limit=0,
				)

	def test_whitelisted_download_sets_binary_response_without_database_writes(self):
		self._submitted_event_with_addendum_and_file()
		before = frappe.db.count("File")
		frappe.set_user(self.care_manager)
		audit_export.download_medication_audit_bundle(self.participant_a)
		self.assertEqual(frappe.local.response.type, "binary")
		self.assertTrue(frappe.local.response.filename.endswith(".zip"))
		self._read_bundle(frappe.local.response.filecontent)
		self.assertEqual(frappe.db.count("File"), before)

	def test_ui_permission_probe_matches_server_authorization(self):
		self._submitted_event_with_addendum_and_file()
		frappe.set_user(self.care_manager)
		self.assertTrue(audit_export.can_download_medication_audit_bundle(self.participant_a))
		frappe.set_user(self.worker)
		self.assertFalse(audit_export.can_download_medication_audit_bundle(self.participant_a))

	def test_child_dated_evidence_selects_intersecting_parents_and_complete_children(self):
		inside = nowdate()
		outside = add_days(nowdate(), -30)
		families = (
			(
				"Participant Drug Count",
				"Drug Count Entry",
				"drug_count_entries",
				{"webster_pak_type": "Regular Daily Webster", "docstatus": 1},
			),
			(
				"Shift Medication Check",
				"Shift Medication Check Entry",
				"check_entries",
				{"month": "January", "docstatus": 1},
			),
			(
				"Discarded Medication Register",
				"Discarded Medication Item",
				"discarded_items",
				{"disposal_status": "Finalized", "docstatus": 1},
			),
		)
		selected = []
		excluded = []
		for parent_doctype, child_doctype, child_field, values in families:
			parent, children = self._insert_dated_parent(
				parent_doctype,
				child_doctype,
				child_field,
				self.participant_a,
				[inside, outside],
				**values,
			)
			outside_parent, _ = self._insert_dated_parent(
				parent_doctype,
				child_doctype,
				child_field,
				self.participant_a,
				[outside],
				**values,
			)
			selected.append((parent_doctype, parent.name, child_doctype, {row.name for row in children}))
			excluded.append((parent_doctype, outside_parent.name))

		data = self._read_bundle(
			audit_export.build_medication_audit_bundle(
				self.participant_a,
				user=self.care_manager,
				from_date=inside,
				to_date=inside,
			)
		)["records.json"]
		for parent_doctype, parent_name, child_doctype, child_names in selected:
			self.assertIn(parent_name, {row["name"] for row in data[parent_doctype]})
			self.assertTrue(child_names.issubset({row["name"] for row in data[child_doctype]}))
		for parent_doctype, parent_name in excluded:
			self.assertNotIn(parent_name, {row["name"] for row in data[parent_doctype]})

	def test_finalized_lifecycle_excludes_draft_and_cancelled_evidence(self):
		plan, submitted, addendum, _file = self._submitted_event_with_addendum_and_file()
		draft = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": self.participant_a,
				"medication_plan": plan.name,
				"medication_plan_item": plan.medication_items[0].name,
				"actual_datetime": f"{nowdate()} 09:00:00",
				"worker": self.worker,
				"outcome": "Administered",
			}
		)
		draft.db_insert()
		cancelled = frappe.get_doc(
			{
				"doctype": "Medication Administration Event",
				"participant": self.participant_a,
				"medication_plan": plan.name,
				"medication_plan_item": plan.medication_items[0].name,
				"actual_datetime": f"{nowdate()} 10:00:00",
				"worker": self.worker,
				"outcome": "Administered",
				"docstatus": 2,
			}
		)
		cancelled.db_insert()
		records = self._read_bundle(
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
		)["records.json"]
		events = {row["name"]: row for row in records["Medication Administration Event"]}
		self.assertIn(submitted.name, events)
		self.assertEqual(events[submitted.name]["docstatus"], 1)
		self.assertNotIn(draft.name, events)
		self.assertNotIn(cancelled.name, events)
		self.assertEqual(records["Medication Event Addendum"][0]["name"], addendum.name)
		self.assertEqual(records["Medication Event Addendum"][0]["docstatus"], 1)

	def test_child_dated_families_require_finalized_parent(self):
		selected, selected_children = self._insert_dated_parent(
			"Participant Drug Count",
			"Drug Count Entry",
			"drug_count_entries",
			self.participant_a,
			[nowdate(), add_days(nowdate(), -1)],
			webster_pak_type="Regular Daily Webster",
			docstatus=1,
		)
		draft, _ = self._insert_dated_parent(
			"Participant Drug Count",
			"Drug Count Entry",
			"drug_count_entries",
			self.participant_a,
			[nowdate()],
			webster_pak_type="Regular Daily Webster",
		)
		cancelled, _ = self._insert_dated_parent(
			"Participant Drug Count",
			"Drug Count Entry",
			"drug_count_entries",
			self.participant_a,
			[nowdate()],
			webster_pak_type="Regular Daily Webster",
			docstatus=2,
		)
		records = self._read_bundle(
			audit_export.build_medication_audit_bundle(
				self.participant_a, user=self.care_manager, from_date=nowdate(), to_date=nowdate()
			)
		)["records.json"]
		parents = {row["name"]: row for row in records["Participant Drug Count"]}
		self.assertEqual(parents[selected.name]["docstatus"], 1)
		self.assertNotIn(draft.name, parents)
		self.assertNotIn(cancelled.name, parents)
		self.assertTrue(
			{row.name for row in selected_children}.issubset(
				{row["name"] for row in records["Drug Count Entry"]}
			)
		)

	def test_authoritative_plan_lifecycle_is_enforced(self):
		plan, _event, _addendum, _file = self._submitted_event_with_addendum_and_file()
		for status in ("Active", "Superseded", "Archived"):
			frappe.db.set_value(
				"Medication Administration Log", plan.name, "plan_status", status, update_modified=False
			)
			records = self._read_bundle(
				audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
			)["records.json"]
			self.assertIn(plan.name, {row["name"] for row in records["Medication Administration Log"]})
		for status in ("Draft", "Needs Review"):
			frappe.db.set_value(
				"Medication Administration Log", plan.name, "plan_status", status, update_modified=False
			)
			with self.assertRaises(frappe.ValidationError):
				audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)

	def test_in_range_event_includes_older_referenced_plan_and_item(self):
		plan, event, _addendum, _file = self._submitted_event_with_addendum_and_file()
		frappe.db.set_value(
			"Medication Administration Log",
			plan.name,
			"week_commencing",
			add_days(nowdate(), -90),
			update_modified=False,
		)
		data = self._read_bundle(
			audit_export.build_medication_audit_bundle(
				self.participant_a,
				user=self.care_manager,
				from_date=nowdate(),
				to_date=nowdate(),
			)
		)["records.json"]
		self.assertIn(plan.name, {row["name"] for row in data["Medication Administration Log"]})
		self.assertIn(event.medication_plan_item, {row["name"] for row in data["Medication Plan Item"]})

	def test_cross_participant_referenced_plan_fails_closed(self):
		_plan, event, _addendum, _file = self._submitted_event_with_addendum_and_file()
		other_plan, _task = self._active_plan_and_task(participant=self.participant_b)
		frappe.db.set_value(
			"Medication Administration Event",
			event.name,
			{
				"medication_plan": other_plan.name,
				"medication_plan_item": other_plan.medication_items[0].name,
			},
			update_modified=False,
		)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(
				self.participant_a,
				user=self.care_manager,
				from_date=nowdate(),
				to_date=nowdate(),
			)
		frappe.db.set_value(
			"Medication Administration Event",
			event.name,
			{"medication_plan": "missing-plan", "medication_plan_item": "missing-item"},
			update_modified=False,
		)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(
				self.participant_a,
				user=self.care_manager,
				from_date=nowdate(),
				to_date=nowdate(),
			)

	def test_final_record_limit_applies_after_referential_closure(self):
		records = {
			"Medication Administration Log": [
				{"name": "initial-plan"},
				{"name": "referenced-plan"},
			]
		}
		with patch.object(audit_export, "MAX_EXPORT_RECORDS_PER_DOCTYPE", 1):
			with self.assertRaises(frappe.ValidationError):
				audit_export._validate_final_record_limits(records)

	def test_attachment_query_is_bounded_by_remaining_allowance(self):
		file_rows = [frappe._dict(name="file-a"), frappe._dict(name="file-b")]
		with (
			patch.object(audit_export, "MAX_EXPORT_ATTACHMENTS", 1),
			patch.object(audit_export.frappe, "get_all", return_value=file_rows) as get_all,
		):
			with self.assertRaises(frappe.ValidationError):
				audit_export._collect_retained_attachment_inventory(
					{"Medication Administration Event": [{"name": "event-a"}]}
				)
		get_all.assert_called_once()
		self.assertEqual(get_all.call_args.kwargs["limit"], 2)

	def test_attachment_queries_are_batched_by_target_doctype(self):
		records = {
			"Medication Administration Event": [{"name": "event-a"}, {"name": "event-b"}],
			"Incident": [{"name": "incident-a"}],
		}
		with patch.object(audit_export.frappe, "get_all", return_value=[]) as get_all:
			self.assertEqual(audit_export._collect_retained_attachment_inventory(records), [])
		self.assertEqual(get_all.call_count, 2)
		first_filters = get_all.call_args_list[0].kwargs["filters"]
		self.assertEqual(first_filters["attached_to_name"], ["in", ["incident-a"]])
		second_filters = get_all.call_args_list[1].kwargs["filters"]
		self.assertEqual(second_filters["attached_to_name"], ["in", ["event-a", "event-b"]])
		self.assertTrue(
			all(
				call.kwargs["limit"] == audit_export.MAX_EXPORT_ATTACHMENTS + 1
				for call in get_all.call_args_list
			)
		)

	def test_version_queries_are_batched_and_limits_fail_closed(self):
		records = {
			"Medication Administration Event": [{"name": "event-a"}, {"name": "event-b"}],
			"Incident": [{"name": "incident-a"}],
		}
		with patch.object(audit_export.frappe, "get_all", return_value=[]) as get_all:
			self.assertEqual(audit_export._collect_version_metadata(records), [])
		self.assertEqual(get_all.call_count, 2)
		self.assertEqual(
			get_all.call_args_list[0].kwargs["filters"]["docname"], ["in", ["event-a", "event-b"]]
		)
		self.assertTrue(
			all(
				call.kwargs["limit"] == audit_export.MAX_EXPORT_VERSIONS + 1
				for call in get_all.call_args_list
			)
		)

		versions = [
			frappe._dict(name="version-a", ref_doctype="Incident", docname="incident-a"),
			frappe._dict(name="version-b", ref_doctype="Incident", docname="incident-a"),
		]
		with (
			patch.object(audit_export, "MAX_EXPORT_VERSIONS", 1),
			patch.object(audit_export.frappe, "get_all", return_value=versions),
			self.assertRaises(frappe.ValidationError),
		):
			audit_export._collect_version_metadata({"Incident": [{"name": "incident-a"}]})
		with (
			patch.object(audit_export, "MAX_EXPORT_VERSIONS", 2),
			patch.object(audit_export, "MAX_EXPORT_VERSIONS_PER_RECORD", 1),
			patch.object(audit_export.frappe, "get_all", return_value=versions),
			self.assertRaises(frappe.ValidationError),
		):
			audit_export._collect_version_metadata({"Incident": [{"name": "incident-a"}]})
		with (
			patch.object(audit_export, "MAX_EXPORT_VERSIONS", 2),
			patch.object(audit_export, "MAX_EXPORT_VERSIONS_PER_RECORD", 2),
			patch.object(audit_export.frappe, "get_all", return_value=versions),
		):
			self.assertEqual(
				len(audit_export._collect_version_metadata({"Incident": [{"name": "incident-a"}]})), 2
			)

	def test_attachment_hashing_is_streamed_and_byte_bounded(self):
		content = b"abcdefgh"
		row = self._attachment_row(content)
		with (
			patch("care_management.care_management.audit_export.get_file_path", return_value="synthetic"),
			patch("builtins.open", return_value=io.BytesIO(content)),
			patch.object(audit_export, "ATTACHMENT_READ_CHUNK_BYTES", 3),
		):
			item, validated_bytes = audit_export._validated_attachment(row, validated_bytes=0)
		self.assertEqual(validated_bytes, len(content))
		self.assertEqual(item["sha256"], hashlib.sha256(content).hexdigest())
		self.assertNotIn("bytearray", inspect.getsource(audit_export._validated_attachment))

		with (
			patch.object(audit_export, "MAX_EXPORT_ATTACHMENT_BYTES", len(content)),
			patch("care_management.care_management.audit_export.get_file_path", return_value="synthetic"),
			patch("builtins.open", return_value=io.BytesIO(content)),
		):
			audit_export._validated_attachment(row, validated_bytes=0)
		with (
			patch.object(audit_export, "MAX_EXPORT_ATTACHMENT_BYTES", len(content) - 1),
			patch("builtins.open") as open_file,
			self.assertRaises(frappe.ValidationError),
		):
			audit_export._validated_attachment(row, validated_bytes=0)
		open_file.assert_not_called()

	def test_attachment_aggregate_stored_and_actual_overflow_fail_closed(self):
		content = b"abcdef"
		row = self._attachment_row(content)
		with (
			patch.object(audit_export, "MAX_EXPORT_TOTAL_ATTACHMENT_BYTES", 10),
			patch("builtins.open") as open_file,
			self.assertRaises(frappe.ValidationError),
		):
			audit_export._validated_attachment(row, validated_bytes=5)
		open_file.assert_not_called()

		misstated = self._attachment_row(content, file_size=4)
		with (
			patch.object(audit_export, "MAX_EXPORT_TOTAL_ATTACHMENT_BYTES", 5),
			patch.object(audit_export, "ATTACHMENT_READ_CHUNK_BYTES", 2),
			patch("care_management.care_management.audit_export.get_file_path", return_value="synthetic"),
			patch("builtins.open", return_value=io.BytesIO(content)),
			self.assertRaises(frappe.ValidationError),
		):
			audit_export._validated_attachment(misstated, validated_bytes=0)

	def test_incident_references_fail_closed_and_preserve_valid_rows(self):
		incident_a = self._incident()
		incident_b = self._incident()
		records = {
			"Medication Administration Event": [{"name": "event-a", "incident": incident_a.name}],
			"Controlled Medication Transaction": [{"name": "transaction-a", "incident": incident_b.name}],
		}
		rows = audit_export._collect_medication_incidents(self.participant_a, records)
		self.assertEqual({row["name"] for row in rows}, {incident_a.name, incident_b.name})

		records["Medication Administration Event"][0]["incident"] = "missing-incident"
		with self.assertRaises(frappe.ValidationError):
			audit_export._collect_medication_incidents(self.participant_a, records)

		other_incident = self._incident(self.participant_b)
		records["Medication Administration Event"][0]["incident"] = other_incident.name
		with self.assertRaises(frappe.ValidationError):
			audit_export._collect_medication_incidents(self.participant_a, records)

		with patch.object(audit_export, "MAX_EXPORT_RECORDS_PER_DOCTYPE", 1):
			with self.assertRaises(frappe.ValidationError):
				audit_export._validate_final_record_limits({"Incident": rows})

	def test_conflicting_medication_plan_item_claims_fail_closed(self):
		plan_a, _task_a = self._active_plan_and_task()
		frappe.db.set_value(
			"Medication Administration Log",
			plan_a.name,
			"plan_status",
			"Superseded",
			update_modified=False,
		)
		plan_b, _task_b = self._active_plan_and_task()
		item_name = plan_a.medication_items[0].name
		records = {
			"Medication Administration Log": [],
			"Medication Plan Item": [],
			"Medication Administration Event": [
				{
					"name": "conflicting-claim",
					"medication_plan": plan_b.name,
					"medication_plan_item": item_name,
				},
				{
					"name": "authoritative-claim",
					"medication_plan": plan_a.name,
					"medication_plan_item": item_name,
				},
			],
		}
		with self.assertRaises(frappe.ValidationError):
			audit_export._include_referenced_medication_plans(self.participant_a, records)

	def test_manifest_authenticates_every_serialized_content_member(self):
		self._submitted_event_with_addendum_and_file()
		members = self._raw_bundle_members(
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
		)
		manifest = json.loads(members["manifest.json"])
		audit_export.verify_bundle_content(manifest, members)
		for name in ("records.json", "attachments.json", "versions.json"):
			with self.subTest(name=name):
				tampered = dict(members)
				tampered[name] = tampered[name] + b" "
				with self.assertRaises(frappe.ValidationError):
					audit_export.verify_bundle_content(manifest, tampered)
		canonical = audit_export._json_bytes({"b": 2, "a": 1})
		self.assertEqual(
			hashlib.sha256(canonical).hexdigest(),
			hashlib.sha256(audit_export._json_bytes({"a": 1, "b": 2})).hexdigest(),
		)

	def test_attachment_inventory_rejects_public_missing_and_mismatched_files(self):
		_plan, _event, _addendum, file_doc = self._submitted_event_with_addendum_and_file()
		original_path = get_file_path(file_doc.name)
		frappe.db.set_value("File", file_doc.name, "is_private", 0, update_modified=False)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
		frappe.db.set_value("File", file_doc.name, "is_private", 1, update_modified=False)

		with patch(
			"care_management.care_management.audit_export.get_file_path",
			return_value=f"{original_path}.missing",
		):
			with self.assertRaises(frappe.ValidationError):
				audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)

		frappe.db.set_value(
			"File", file_doc.name, "file_size", (file_doc.file_size or 0) + 1, update_modified=False
		)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
		frappe.db.set_value(
			"File", file_doc.name, "file_size", os.path.getsize(original_path), update_modified=False
		)
		frappe.db.set_value(
			"File", file_doc.name, "content_hash", "invalid-content-hash", update_modified=False
		)
		with self.assertRaises(frappe.ValidationError):
			audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)

	def test_global_version_and_serialized_size_limits_fail_closed(self):
		self._submitted_event_with_addendum_and_file()
		with (
			patch.object(audit_export, "MAX_EXPORT_VERSIONS", 0),
			patch.object(
				audit_export.frappe,
				"get_all",
				return_value=[
					frappe._dict(
						name="synthetic-version",
						ref_doctype="Medication Administration Event",
						docname="synthetic-event",
					)
				],
			),
		):
			with self.assertRaises(frappe.ValidationError):
				audit_export._collect_version_metadata(
					{"Medication Administration Event": [{"name": "synthetic-event"}]}
				)
		with patch.object(audit_export, "MAX_EXPORT_UNCOMPRESSED_BYTES", 1):
			with self.assertRaises(frappe.ValidationError):
				audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
