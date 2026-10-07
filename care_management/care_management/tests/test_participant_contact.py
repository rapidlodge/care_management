import frappe
from frappe.tests import IntegrationTestCase

CASES = [
	("doctype", lambda m: m.name == "Participant Contact"),
	("opaque_name", lambda m: m.autoname == "hash"),
	("participant_link", lambda m: m.get_field("participant").options == "Participant Profile"),
	("participant_required", lambda m: bool(m.get_field("participant").reqd)),
	("participant_once", lambda m: bool(m.get_field("participant").set_only_once)),
	("type_required", lambda m: bool(m.get_field("contact_type").reqd)),
	("emergency_type", lambda m: "Emergency Contact" in m.get_field("contact_type").options),
	("pharmacist_type", lambda m: "Pharmacist" in m.get_field("contact_type").options),
	("priority_required", lambda m: bool(m.get_field("priority").reqd)),
	("status_required", lambda m: bool(m.get_field("status").reqd)),
	("verification", lambda m: m.has_field("verification_status")),
	("review_date", lambda m: m.has_field("review_date")),
	("availability", lambda m: m.has_field("availability_notes")),
	("unreachable", lambda m: m.has_field("unable_to_reach_instruction")),
	("effective_from", lambda m: m.has_field("effective_from")),
	("effective_to", lambda m: m.has_field("effective_to")),
	("tracked", lambda m: bool(m.track_changes)),
	("no_import", lambda m: not bool(m.allow_import)),
	("no_rename", lambda m: not bool(m.allow_rename)),
	("no_authority_field", lambda m: not any(m.has_field(f) for f in ("consent_authority", "legal_authority", "guardian"))),
]


class TestParticipantContact(IntegrationTestCase):
	pass


def _test(predicate):
	def run(self):
		self.assertTrue(predicate(frappe.get_meta("Participant Contact")))
	return run


for _name, _predicate in CASES:
	setattr(TestParticipantContact, f"test_contact_{_name}", _test(_predicate))
