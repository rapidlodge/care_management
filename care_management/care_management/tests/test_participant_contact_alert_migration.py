import inspect
import json
from pathlib import Path

import frappe
from frappe.tests import IntegrationTestCase
from care_management.patches.v1_0 import migrate_participant_contacts_and_health_alerts as migration

FIXTURE = Path(frappe.get_app_path("care_management", "fixtures", "role.json"))
CASES = [
	("two_roles", lambda: len(migration.ROLE_DEFINITIONS) == 2),
	("clinical_role", lambda: "Clinical Lead" in migration.ROLE_DEFINITIONS),
	("privacy_role", lambda: "Privacy Officer" in migration.ROLE_DEFINITIONS),
	("roles_enabled", lambda: all(not d["disabled"] for d in migration.ROLE_DEFINITIONS.values())),
	("roles_desk", lambda: all(d["desk_access"] for d in migration.ROLE_DEFINITIONS.values())),
	("roles_standard", lambda: all(not d["is_custom"] for d in migration.ROLE_DEFINITIONS.values())),
	("fixture_exists", lambda: FIXTURE.is_file()),
	("fixture_two", lambda: len(json.loads(FIXTURE.read_text())) == 2),
	("fixture_names", lambda: {d["role_name"] for d in json.loads(FIXTURE.read_text())} == set(migration.ROLE_DEFINITIONS)),
	("bootstrap_callable", lambda: callable(migration.bootstrap_specialist_roles)),
	("after_callable", lambda: callable(migration.run_guarded_migration)),
	("bootstrap_no_user", lambda: "User" not in inspect.getsource(migration.bootstrap_specialist_roles)),
	("bootstrap_no_share", lambda: "DocShare" not in inspect.getsource(migration.bootstrap_specialist_roles)),
	("bootstrap_no_user_permission", lambda: "User Permission" not in inspect.getsource(migration.bootstrap_specialist_roles)),
	("bounded_source", lambda: '"Participant Profile"' in inspect.getsource(migration.run_guarded_migration)),
	("three_schema_checks", lambda: inspect.getsource(migration.run_guarded_migration).count("Participant ") >= 3),
	("before_install_hook", lambda: "bootstrap_specialist_roles" in str(frappe.get_hooks("before_install", app_name="care_management"))),
	("before_migrate_hook", lambda: "bootstrap_specialist_roles" in str(frappe.get_hooks("before_migrate", app_name="care_management"))),
	("after_sync_hook", lambda: "run_guarded_migration" in str(frappe.get_hooks("after_sync", app_name="care_management"))),
	("after_migrate_hook", lambda: "run_guarded_migration" in str(frappe.get_hooks("after_migrate", app_name="care_management"))),
]


class TestParticipantContactAlertMigration(IntegrationTestCase): pass

def _test(predicate):
	def run(self): self.assertTrue(predicate())
	return run

for _name, _predicate in CASES:
	setattr(TestParticipantContactAlertMigration, f"test_migration_{_name}", _test(_predicate))
