
import pathlib
import sys
import tempfile
sys.path.insert(0, 'scripts')

import gh
import config
import deskwork
from unittest.mock import patch, MagicMock
import argparse

# Track writes
write_calls = []

def mock_api_write_detector(path, method="GET", body=None, extra_args=None):
    if method != "GET":
        write_calls.append(("api", path, method))
    # Return dummy data
    if 'paginate' in str(extra_args or []):
        return []
    if 'labels' in path:
        if method == 'POST':
            return {'name': 'test'}
        return {'name': 'test', 'color': 'FF0000'}
    if 'issues' in path and method == 'POST':
        return {'number': 42, 'node_id': 'I_42'}
    if path.endswith('/issues'):
        return []  # Empty list of issues
    return None

def mock_graphql(query, **kw):
    if 'createProjectV2Field' in query:
        return {"createProjectV2Field": {"field": {"id": "F_1", "name": "Status", "options": []}}}
    return {"node": {"fields": {"nodes": []}}}

# Test 1: capture --dry-run
print("Test 1: capture --dry-run")
with tempfile.TemporaryDirectory() as tmpdir:
    repo = pathlib.Path(tmpdir)
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text('[remote "origin"]\n    url = https://github.com/owner/repo.git\n')
    (repo / ".github").mkdir()
    config_text = """enabled = true
project = "PVT_kwDOABCD1234"
designs = "DESIGNS.md"
roadmap = "ROADMAP.md"
issue_types = ["Task", "Bug"]
[labels]
area = ["area:web", "area:api"]
[fields]
Status = ["Todo", "Done"]
Effort = ["M", "L"]
Risk = ["Low", "High"]
"""
    (repo / ".github" / "deskwork.toml").write_text(config_text)
    
    with patch('gh.api', side_effect=mock_api_write_detector):
        with patch('ids.node_id', return_value='I_test'):
            args = argparse.Namespace(mode='capture', repo=repo, title='Test', issue_type=None, area=None, dry_run=True)
            cfg = config.load(repo)
            write_calls.clear()
            result = deskwork.mode_capture(args, cfg)
            
            if any(call[2] != 'GET' for call in write_calls):
                print(f"  FAIL: capture --dry-run made writes: {[c for c in write_calls if c[2] != 'GET']}")
                sys.exit(1)
            print("  PASS: capture --dry-run made no write calls")

# Test 2: init --dry-run
print("Test 2: init --dry-run")
with tempfile.TemporaryDirectory() as tmpdir:
    repo = pathlib.Path(tmpdir)
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text('[remote "origin"]\n    url = https://github.com/owner/repo.git\n')
    (repo / ".github").mkdir()
    (repo / ".github" / "deskwork.toml").write_text(config_text)
    
    with patch('gh.api', side_effect=mock_api_write_detector):
        with patch('gh.graphql', side_effect=mock_graphql):
            args = argparse.Namespace(mode='init', repo=repo, title=None, issue_type=None, area=None, dry_run=True)
            cfg = config.load(repo)
            write_calls.clear()
            result = deskwork.mode_init(args, cfg)
            
            if any(call[2] != 'GET' for call in write_calls if len(call) > 2):
                print(f"  FAIL: init --dry-run made writes: {[c for c in write_calls if len(c) > 2 and c[2] != 'GET']}")
                sys.exit(1)
            print("  PASS: init --dry-run made no write calls")

# Test 3: intake --dry-run
print("Test 3: intake --dry-run")
with tempfile.TemporaryDirectory() as tmpdir:
    repo = pathlib.Path(tmpdir)
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text('[remote "origin"]\n    url = https://github.com/owner/repo.git\n')
    (repo / ".github").mkdir()
    (repo / ".github" / "deskwork.toml").write_text(config_text)
    
    def mock_graphql_intake(query, **kw):
        return {"node": {"items": {"nodes": []}}}
    
    with patch('gh.api', side_effect=mock_api_write_detector):
        with patch('gh.graphql', side_effect=mock_graphql_intake):
            with patch('ids.node_id', return_value='I_test'):
                args = argparse.Namespace(mode='intake', repo=repo, title=None, issue_type=None, area=None, dry_run=True)
                cfg = config.load(repo)
                write_calls.clear()
                result = deskwork.mode_intake(args, cfg)
                
                if any(call[2] != 'GET' for call in write_calls if len(call) > 2):
                    print(f"  FAIL: intake --dry-run made writes: {[c for c in write_calls if len(c) > 2 and c[2] != 'GET']}")
                    sys.exit(1)
                print("  PASS: intake --dry-run made no write calls")

print("\nAll dry-run tests PASSED")
