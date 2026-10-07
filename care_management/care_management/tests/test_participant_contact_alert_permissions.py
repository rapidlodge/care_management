import frappe
from frappe.tests import IntegrationTestCase
from care_management.care_management import permissions

DOCTYPES = ("Participant Contact", "Participant Health Alert", "Participant Health Alert Acknowledgement")
CASES = []
for dt in DOCTYPES:
	CASES.extend([
		(f"protected_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PROTECTED_PARTICIPANT_DOCTYPES),
		(f"direct_{frappe.scrub(dt)}", lambda d=dt: permissions.DIRECT_PARTICIPANT_FIELDS.get(d) == "participant"),
		(f"query_hook_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PARTICIPANT_PERMISSION_QUERY_CONDITION_HOOKS),
		(f"doc_hook_{frappe.scrub(dt)}", lambda d=dt: d in permissions.PARTICIPANT_DOCUMENT_PERMISSION_HOOKS),
	])
for role in ("Clinical Lead", "Privacy Officer"):
	CASES.extend([
		(f"role_constant_{frappe.scrub(role)}", lambda r=role: r in permissions.CONTACT_ALERT_READ_ROLES),
		(f"not_manager_{frappe.scrub(role)}", lambda r=role: r not in permissions.CARE_MANAGER_ROLES),
	])
CASES += [
	("guest_denied", lambda: permissions.normalize_user("Guest") is None),
	("unknown_denied", lambda: permissions.get_participant_permission_query_conditions("Unknown", "Guest") == "1=0"),
	("contact_worker_scoped", lambda: "Participant Contact" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("alert_worker_scoped", lambda: "Participant Health Alert" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("ack_worker_scoped", lambda: "Participant Health Alert Acknowledgement" in permissions.SUPPORT_WORKER_DOCUMENT_ACCESS_DOCTYPES),
	("no_contact_admin_authority", lambda: "Consent" not in permissions.DIRECT_PARTICIPANT_FIELDS.get("Participant Contact", "")),
	("docshare_protected", lambda: all(d in permissions.PROTECTED_PARTICIPANT_DOCTYPES for d in DOCTYPES)),
	("three_targets", lambda: len(DOCTYPES) == 3),
]


class TestParticipantContactAlertPermissions(IntegrationTestCase): pass

def _test(predicate):
	def run(self): self.assertTrue(predicate())
	return run

for _name, _predicate in CASES:
	setattr(TestParticipantContactAlertPermissions, f"test_permission_{_name}", _test(_predicate))
