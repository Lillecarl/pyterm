#!/usr/bin/env agent-python
"""Point the references in open Lillecarl/pyterm issues at their new numbers.

  rewrite_open.py            dry run: one JSON line per body or comment it would edit
  rewrite_open.py --apply    edit through GraphQL; each text as it was goes to rewrite-open.jsonl

A transfer rewrote a bare `#N` to `Lillecarl/pyterm#M` when issue N had moved
already, and to `Lillecarl/pymux#N` when it had not. Both become `#M`. Text an
outsider wrote is left alone: editing it speaks in their name.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
TARGET = "Lillecarl/pyterm"
INSIDERS = {"OWNER", "MEMBER", "COLLABORATOR"}
APPLY = "--apply" in sys.argv

db = sqlite3.connect(HERE / "issues.sqlite")
NEW = dict(db.execute("select old, new from moves where repo = 'pymux'"))

OLD_URL = re.compile(r"https://github\.com/Lillecarl/pymux/issues/(\d+)\b")
OLD = re.compile(r"(?<![\w/.-])Lillecarl/pymux#(\d+)\b")
SELF = re.compile(r"(?<![\w/.-])Lillecarl/pyterm#(\d+)\b")

Q = """
query($n:Int!){repository(owner:"Lillecarl",name:"pyterm"){issue(number:$n){
  id body authorAssociation comments(first:100){totalCount nodes{id body authorAssociation}}}}}"""


def gh(*args: str) -> str:
    return subprocess.run(["gh", *args], capture_output=True, text=True, check=True).stdout


def rewrite(text: str) -> str:
    text = OLD_URL.sub(
        lambda m: f"https://github.com/{TARGET}/issues/{NEW[int(m[1])]}" if int(m[1]) in NEW else m[0], text
    )
    text = OLD.sub(lambda m: f"#{NEW[int(m[1])]}" if int(m[1]) in NEW else m[0], text)
    return SELF.sub(r"#\1", text)


def update(kind: str, node: str, body: str) -> None:
    mutation = {"issue": "updateIssue", "comment": "updateIssueComment"}[kind]
    query = f"mutation($i:ID!,$b:String!){{{mutation}(input:{{id:$i,body:$b}}){{clientMutationId}}}}"
    gh("api", "graphql", "-f", f"query={query}", "-f", f"i={node}", "-f", f"b={body}")


def main() -> None:
    numbers = sorted(
        new
        for (new,) in db.execute(
            "select new from moves m join issues i on i.repo = m.repo and i.number = m.old where i.state = 'OPEN'"
        )
    )
    edits = 0
    with (HERE / "rewrite-open.jsonl").open("a") as log:
        for n in numbers:
            issue = json.loads(gh("api", "graphql", "-f", f"query={Q}", "-F", f"n={n}"))["data"]["repository"]["issue"]
            if issue["comments"]["totalCount"] > len(issue["comments"]["nodes"]):
                print(f"#{n}: comments truncated", file=sys.stderr)
            targets = [("issue", issue["id"], issue["body"], issue["authorAssociation"])] + [
                ("comment", c["id"], c["body"], c["authorAssociation"]) for c in issue["comments"]["nodes"]
            ]
            for kind, node, body, association in targets:
                new = rewrite(body)
                if new == body:
                    continue
                if association not in INSIDERS:
                    print(f"#{n} {kind} {node}: an outsider wrote it, left alone", file=sys.stderr)
                    continue
                edits += 1
                print(json.dumps({"issue": n, "kind": kind, "id": node}), flush=True)
                if APPLY:
                    log.write(json.dumps({"issue": n, "kind": kind, "id": node, "before": body}) + "\n")
                    log.flush()
                    update(kind, node, new)
                    time.sleep(1)
    print(f"{edits} edits{'' if APPLY else ' (dry run)'}", file=sys.stderr)


main()
