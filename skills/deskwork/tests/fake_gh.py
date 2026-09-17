#!/usr/bin/env python3
"""Stand-in for the gh CLI. Prints a canned response keyed on argv."""
import json
import os
import sys

responses = json.loads(open(os.environ["DESKWORK_FAKE_GH"]).read())
key = " ".join(sys.argv[1:])
if key not in responses:
    sys.stderr.write(f"fake_gh: no canned response for: {key}\n")
    sys.exit(1)
entry = responses[key]
sys.stdout.write(entry["stdout"])
sys.exit(entry.get("exit", 0))
