import frappe
from frappe.tests import IntegrationTestCase

FIELDS = ["participant","category","severity","concise_summary","response_instruction","supporting_detail","source_type","source_reference","verification_status","verified_by","verified_on","effective_from","effective_to","review_date","status","responsible_role","responsible_user","acknowledgement_required","resolved_by","resolved_on","resolution_reason"]
CASES = [(f"field_{field}", lambda m, f=field: m.has_field(f)) for field in FIELDS]
CASES += [
	("opaque_name", lambda m: m.autoname == "hash"),
	("tracked", lambda m: bool(m.track_changes)),
	("participant_link", lambda m: m.get_field("participant").options == "Participant Profile"),
	("supporting_detail_restricted", lambda m: int(m.get_field("supporting_detail").permlevel or 0) == 1),
	("draft_status", lambda m: "Draft" in m.get_field("status").options),
	("active_status", lambda m: "Active" in m.get_field("status").options),
	("resolved_status", lambda m: "Resolved" in m.get_field("status").options),
	("view_not_ack", lambda m: not m.has_field("viewed_on")),
]


class TestParticipantHealthAlert(IntegrationTestCase):
	pass


def _test(predicate):
	def run(self): self.assertTrue(predicate(frappe.get_meta("Participant Health Alert")))
	return run


for _name, _predicate in CASES:
	setattr(TestParticipantHealthAlert, f"test_alert_{_name}", _test(_predicate))
