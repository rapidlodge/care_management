import hashlib
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
				{"webster_pak_type": "Regular Daily Webster"},
			),
			("Shift Medication Check", "Shift Medication Check Entry", "check_entries", {"month": "January"}),
			(
				"Discarded Medication Register",
				"Discarded Medication Item",
				"discarded_items",
				{"disposal_status": "Finalized"},
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
				audit_export,
				"_get_rows",
				return_value=[{"name": "synthetic-version"}],
			),
		):
			with self.assertRaises(frappe.ValidationError):
				audit_export._collect_version_metadata(
					{"Medication Administration Event": [{"name": "synthetic-event"}]}
				)
		with patch.object(audit_export, "MAX_EXPORT_UNCOMPRESSED_BYTES", 1):
			with self.assertRaises(frappe.ValidationError):
				audit_export.build_medication_audit_bundle(self.participant_a, user=self.care_manager)
