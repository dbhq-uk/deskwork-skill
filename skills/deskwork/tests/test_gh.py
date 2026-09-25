import json
import subprocess

import pytest

import gh


class Recorder:
    """Stands in for subprocess.run, so a test can see exactly what reached gh."""

    def __init__(self, stdout="{}"):
        self.calls = []
        self.stdout = stdout

    def __call__(self, argv, input=None, capture_output=True, text=True, cwd=None):
        self.calls.append({"argv": argv, "stdin": input, "cwd": cwd})
        return subprocess.CompletedProcess(argv, 0, stdout=self.stdout, stderr="")


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(gh.subprocess, "run", rec)
    monkeypatch.setattr(gh, "_pace", lambda: None)
    return rec


def test_api_parses_json(fake_gh):
    fake_gh({"api repos/owner/repo/issues/1": {"stdout": '{"id": 42, "number": 1}'}})
    assert gh.api("repos/owner/repo/issues/1")["id"] == 42


def test_api_raises_on_failure(fake_gh):
    fake_gh({"api repos/owner/repo/issues/9": {"stdout": "", "exit": 1}})
    with pytest.raises(gh.GhError):
        gh.api("repos/owner/repo/issues/9")


def test_graphql_sends_variables_as_json_so_lists_survive(recorder):
    recorder.stdout = '{"data": {"ok": true}}'
    options = [{"name": "Triage", "color": "GRAY", "description": "Not yet reviewed"}]
    assert gh.graphql("query($o: [X!]!) { ok }", o=options, flag=True, note=None) == {"ok": True}
    call = recorder.calls[0]
    assert call["argv"] == ["gh", "api", "graphql", "--input", "-"]
    sent = json.loads(call["stdin"])
    assert sent["variables"] == {"o": options, "flag": True, "note": None}


def test_graphql_paces_mutations_only(monkeypatch):
    paced = []
    monkeypatch.setattr(gh, "_pace", lambda: paced.append(True))
    monkeypatch.setattr(gh.subprocess, "run", Recorder('{"data": {}}'))
    gh.graphql("query { viewer { login } }")
    assert paced == []
    gh.graphql("mutation { addStar(input: {starrableId: \"x\"}) { clientMutationId } }")
    assert paced == [True]


@pytest.mark.parametrize("line, expected", [
    ("gh version 2.100.0 (2026-09-03)\nhttps://github.com/cli/cli/releases/tag/v2.100.0\n", (2, 100, 0)),
    ("gh version 2.94.0 (2026-06-10)\n", (2, 94, 0)),
])
def test_version_is_read_from_gh(recorder, line, expected):
    recorder.stdout = line
    assert gh.version() == expected


def test_a_gh_older_than_the_floor_is_refused(recorder):
    recorder.stdout = "gh version 2.93.1 (2026-05-20)\n"
    with pytest.raises(gh.TooOld) as caught:
        gh.require_version()
    assert "2.94.0" in str(caught.value) and "2.93.1" in str(caught.value)


def test_the_floor_itself_is_accepted(recorder):
    recorder.stdout = "gh version 2.94.0 (2026-06-10)\n"
    assert gh.require_version() == (2, 94, 0)


# Constraint 1, enforced where the calls are made. Each case below reaches
# gh.py by a different route, and each must raise before gh is started.

@pytest.mark.parametrize("verb", ["close", "delete", "transfer"])
def test_gh_issue_close_delete_and_transfer_are_refused(recorder, verb):
    with pytest.raises(gh.Refused):
        gh.run(["issue", verb, "5", "-R", "owner/repo"])
    assert recorder.calls == []


@pytest.mark.parametrize("mutation", [
    'mutation { closeIssue(input: {issueId: "I_x"}) { issue { id } } }',
    'mutation { deleteIssue(input: {issueId: "I_x"}) { clientMutationId } }',
    'mutation { transferIssue(input: {issueId: "I_x", repositoryId: "R_x"}) { issue { id } } }',
    'mutation { updateIssue(input: {id: "I_x", state: CLOSED}) { issue { id } } }',
    'mutation($i: UpdateIssueInput!) { updateIssue(input: $i) { issue { id } } }',
])
def test_closing_mutations_through_graphql_are_refused(recorder, mutation):
    with pytest.raises(gh.Refused):
        gh.graphql(mutation, i={"id": "I_x", "state": "CLOSED"})
    assert recorder.calls == []


def test_a_closing_mutation_passed_as_a_raw_field_is_refused(recorder):
    with pytest.raises(gh.Refused):
        gh.run(["api", "graphql", "-f", 'query=mutation { closeIssue(input: {issueId: "I_x"}) { clientMutationId } }'])
    assert recorder.calls == []


@pytest.mark.parametrize("body", [{"state": "closed"}, {"state_reason": "completed"}])
def test_a_patch_carrying_state_is_refused_however_it_is_spaced(recorder, body):
    with pytest.raises(gh.Refused):
        gh.api("repos/owner/repo/issues/5", method="PATCH", body=body)
    with pytest.raises(gh.Refused):
        gh.run(["api", "repos/owner/repo/issues/5", "-X", "PATCH", "--input", "-"],
               stdin_data='{"state":"closed"}')
    assert recorder.calls == []


def test_a_state_field_flag_is_refused_wherever_the_path_sits(recorder):
    with pytest.raises(gh.Refused):
        gh.run(["api", "-X", "PATCH", "repos/owner/repo/issues/5", "-f", "state=closed"])
    with pytest.raises(gh.Refused):
        gh.run(["api", "--method=PATCH", "repos/owner/repo/issues/5", "--raw-field=state=closed"])
    assert recorder.calls == []


@pytest.mark.parametrize("extra", [["-X", "DELETE"], ["-XDELETE"], ["--method", "delete"]])
def test_delete_through_extra_args_is_refused(recorder, extra):
    with pytest.raises(gh.Refused):
        gh.api("repos/owner/repo/issues/5", extra_args=extra)
    with pytest.raises(gh.Refused):
        gh.api("repos/owner/repo/issues/5", method="DELETE")
    assert recorder.calls == []


def test_removing_a_dependency_edge_still_works(recorder):
    gh.api("repos/owner/repo/issues/144/dependencies/blocked_by/3527190001", method="DELETE")
    assert recorder.calls[0]["argv"][:3] == ["gh", "api", "repos/owner/repo/issues/144/dependencies/blocked_by/3527190001"]


def test_ordinary_writes_still_pass(recorder):
    gh.api("repos/owner/repo/issues/5/comments", method="POST", body={"body": "state of play"})
    gh.api("repos/owner/repo/issues/5", method="PATCH", body={"title": "Clearer title"})
    gh.run(["issue", "edit", "5", "--add-label", "triage"], write=True)
    assert len(recorder.calls) == 3
