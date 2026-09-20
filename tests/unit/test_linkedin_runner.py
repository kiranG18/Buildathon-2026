from scripts.linkedin_runner import NOTE_LIMIT, as_sent, pending_notes


def state():
    return {
        "msgs": [{"id": "M1", "ch": "linkedin", "body": "Hi Asha, a note."}, {"id": "M2", "ch": "email", "body": "An email."}, {"id": "M3", "ch": "linkedin", "body": "Sent already."}, {"id": "M4", "ch": "linkedin", "body": "Second note."}],
        "enr": [{"id": "E1", "pid": "asha"}, {"id": "E2", "pid": "ben"}],
        "people": {"asha": {"name": "Asha Rao", "linkedin": "https://www.linkedin.com/in/asha"}, "ben": {"name": "Ben Ito", "linkedin": "linkedin.com/in/ben"}},
        "approvals": [
            {"id": "A2", "eid": "E2", "msgId": "M4", "status": "open", "t": 20},
            {"id": "A1", "eid": "E1", "msgId": "M1", "status": "open", "t": 10},
            {"id": "A3", "eid": "E1", "msgId": "M2", "status": "open", "t": 5},
            {"id": "A4", "eid": "E1", "msgId": "M3", "status": "approved", "t": 1},
            {"id": "A5", "eid": "E1", "msgId": None, "status": "open", "t": 2},
        ],
    }


def test_only_open_linkedin_notes_are_listed_oldest_first_with_their_profile():
    got = pending_notes(state())
    assert [(n["approval"], n["name"], n["url"], n["note"]) for n in got] == [
        ("A1", "Asha Rao", "https://www.linkedin.com/in/asha", "Hi Asha, a note."),
        ("A2", "Ben Ito", "linkedin.com/in/ben", "Second note."),
    ]


def test_a_note_is_cut_to_the_limit_exactly_like_the_bot_does():
    assert as_sent("short") == "short"
    long = "x" * 250
    assert len(as_sent(long)) == NOTE_LIMIT and as_sent(long).endswith("...")
    assert as_sent("y" * NOTE_LIMIT) == "y" * NOTE_LIMIT
