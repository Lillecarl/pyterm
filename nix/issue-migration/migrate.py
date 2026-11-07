#!/usr/bin/env agent-python
"""Transfer every issue of the source repositories into Lillecarl/pyterm, oldest first.

  migrate.py snapshot     every issue, its comments and who wrote them, into issues.sqlite
  migrate.py outsiders    issues where someone other than the owner took part
  migrate.py labels       create the source's labels in the target, colour and description kept
  migrate.py apply [N]    transfer N (default all), one `moves` row each, committed before the next
  migrate.py fixup        restore sub-issue links, which a transfer drops
  migrate.py map          the moves as JSON lines on stdout

Resumable: a row in `moves` is a transfer done, and apply skips it.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

OWNER = "Lillecarl"
TARGET = f"{OWNER}/pyterm"
SOURCES = ["pymux", "pyte", "ptyhost", "ptterm", "txterm", "pysmithay", "ptkhx", "deferimport", "pyterm-pytest"]
DB = Path(__file__).with_name("issues.sqlite")
INSIDERS = {"OWNER", "MEMBER", "COLLABORATOR"}
PAUSE = 3.0

LIST = """
query($owner:String!,$name:String!,$after:String){
  repository(owner:$owner,name:$name){
    hasIssuesEnabled
    issues(first:50,after:$after,orderBy:{field:CREATED_AT,direction:ASC}){
      pageInfo{hasNextPage endCursor}
      nodes{id number title createdAt state stateReason authorAssociation author{login}
            labels(first:30){nodes{name}} assignees(first:10){nodes{login}}
            parent{number repository{nameWithOwner}}
            comments(first:100){totalCount nodes{authorAssociation author{login}}}}
    }
  }
}"""

TRANSFER = """
mutation($i:ID!,$r:ID!){
  transferIssue(input:{issueId:$i,repositoryId:$r,createLabelsIfMissing:true}){
    issue{number url}
  }
}"""

WHERE = """
query($i:ID!){node(id:$i){... on Issue{number url repository{nameWithOwner}}}}"""

LIMIT_HINTS = ("rate limit", "abuse", "502", "503", "504", "timeout", "was submitted too quickly", "secondary")

SCHEMA = """
create table if not exists issues(
  repo text, number integer, node_id text, title text, created_at text, state text,
  state_reason text, author text, author_association text, labels text, assignees text,
  parent_repo text, parent_number integer, comment_count integer, comment_authors text,
  primary key(repo, number));
create table if not exists moves(
  repo text, old integer, new integer, url text, moved_at text,
  primary key(repo, old));
create table if not exists relinks(
  child integer primary key, parent integer, outcome text);
"""


def gh(*args: str) -> str:
    attempt = 0
    while True:
        p = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
        if p.returncode == 0:
            return p.stdout
        if any(h in p.stderr.lower() for h in LIMIT_HINTS):
            attempt += 1
            wait = min(60 * attempt, 900)
            print(f"limited, sleeping {wait}s: {p.stderr.strip()[:200]}", file=sys.stderr, flush=True)
            time.sleep(wait)
            continue
        raise RuntimeError(f"gh {' '.join(args[:4])}: {p.stderr}")


def graphql(query: str, **variables: str | None) -> dict[str, Any]:
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        if v is not None:
            args += ["-f", f"{k}={v}"]
    return json.loads(gh(*args))["data"]


def connect() -> sqlite3.Connection:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def snapshot(db: sqlite3.Connection) -> None:
    for repo in SOURCES:
        after = None
        while True:
            r = graphql(LIST, owner=OWNER, name=repo, after=after)["repository"]
            if not r["hasIssuesEnabled"]:
                print(f"{repo}: issues disabled", file=sys.stderr)
                break
            page = r["issues"]
            for n in page["nodes"]:
                comments = n["comments"]
                if comments["totalCount"] > len(comments["nodes"]):
                    print(f"{repo}#{n['number']}: comments truncated", file=sys.stderr)
                parent = n["parent"] or {}
                db.execute(
                    "insert or replace into issues values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        repo,
                        n["number"],
                        n["id"],
                        n["title"],
                        n["createdAt"],
                        n["state"],
                        n["stateReason"],
                        (n["author"] or {}).get("login"),
                        n["authorAssociation"],
                        json.dumps([x["name"] for x in n["labels"]["nodes"]]),
                        json.dumps([x["login"] for x in n["assignees"]["nodes"]]),
                        (parent.get("repository") or {}).get("nameWithOwner"),
                        parent.get("number"),
                        comments["totalCount"],
                        json.dumps(
                            [[(c["author"] or {}).get("login"), c["authorAssociation"]] for c in comments["nodes"]]
                        ),
                    ),
                )
            db.commit()
            if not page["pageInfo"]["hasNextPage"]:
                break
            after = page["pageInfo"]["endCursor"]
    count = db.execute("select count(*) from issues").fetchone()[0]
    print(json.dumps({"issues": count}))


def outsiders(db: sqlite3.Connection) -> None:
    for row in db.execute("select * from issues order by created_at"):
        people = [(row["author"], row["author_association"])] + [tuple(c) for c in json.loads(row["comment_authors"])]
        foreign = sorted({f"{who} ({assoc})" for who, assoc in people if assoc not in INSIDERS})
        if foreign:
            print(json.dumps({"repo": row["repo"], "number": row["number"], "title": row["title"], "people": foreign}))


def labels(db: sqlite3.Connection) -> None:
    have = {x["name"] for x in json.loads(gh("label", "list", "-R", TARGET, "--limit", "500", "--json", "name"))}
    wanted: dict[str, tuple[str, str]] = {}
    for repo in SOURCES:
        try:
            listed = gh("label", "list", "-R", f"{OWNER}/{repo}", "--limit", "500", "--json", "name,color,description")
        except RuntimeError:
            continue
        for x in json.loads(listed):
            wanted.setdefault(x["name"], (x["color"], x["description"]))
    used = {name for (ls,) in db.execute("select labels from issues") for name in json.loads(ls)}
    for name in sorted(used - have):
        color, description = wanted[name]
        gh("label", "create", name, "-R", TARGET, "--color", color, "--description", description)
        print(json.dumps({"created": name}))


def transfer(node_id: str, target_id: str) -> dict[str, Any]:
    """
    A retried mutation can find its issue moved already: the first try
    timed out on our side and landed on GitHub's. A node id survives a
    transfer, so the node says where the issue is now.
    """
    try:
        return graphql(TRANSFER, i=node_id, r=target_id)["transferIssue"]["issue"]
    except RuntimeError:
        node = graphql(WHERE, i=node_id)["node"]
        if node["repository"]["nameWithOwner"] != TARGET:
            raise
        return node


def apply(db: sqlite3.Connection, limit: int | None) -> None:
    target_id = json.loads(gh("api", f"repos/{TARGET}"))["node_id"]
    todo = db.execute(
        "select i.repo, i.number, i.node_id from issues i"
        " left join moves m on m.repo = i.repo and m.old = i.number"
        " where m.old is null order by i.created_at"
    ).fetchall()[:limit]
    print(f"{len(todo)} to transfer", file=sys.stderr, flush=True)
    for row in todo:
        new = transfer(row["node_id"], target_id)
        db.execute(
            "insert into moves values (?,?,?,?,datetime('now'))",
            (row["repo"], row["number"], new["number"], new["url"]),
        )
        db.commit()
        print(json.dumps({"repo": row["repo"], "old": row["number"], "new": new["number"]}), flush=True)
        time.sleep(PAUSE)


def fixup(db: sqlite3.Connection) -> None:
    new_of = {(f"{OWNER}/{r['repo']}", r["old"]): r["new"] for r in db.execute("select * from moves")}
    rows = db.execute("select * from issues where parent_number is not null order by created_at").fetchall()
    for row in rows:
        child = new_of.get((f"{OWNER}/{row['repo']}", row["number"]))
        key = (row["parent_repo"], row["parent_number"])
        parent = new_of.get(key) or (key[1] if key[0] == TARGET else None)
        if child is None or parent is None:
            print(f"cannot relink {row['repo']}#{row['number']} under {key}", file=sys.stderr)
            continue
        done = db.execute("select outcome from relinks where child = ?", (child,)).fetchone()
        if done and done["outcome"] == "ok":
            continue
        child_id = json.loads(gh("api", f"repos/{TARGET}/issues/{child}"))["id"]
        try:
            gh("api", "-X", "POST", f"repos/{TARGET}/issues/{parent}/sub_issues", "-F", f"sub_issue_id={child_id}")
            outcome = "ok"
        except RuntimeError as e:
            outcome = str(e)[:500]
        db.execute("insert or replace into relinks values (?,?,?)", (child, parent, outcome))
        db.commit()
        print(json.dumps({"child": child, "parent": parent, "outcome": outcome}), flush=True)
        time.sleep(1)


def mapping(db: sqlite3.Connection) -> None:
    for r in db.execute("select repo, old, new from moves order by repo, old"):
        print(json.dumps(dict(r)))


def main() -> None:
    commands = {
        "snapshot": snapshot,
        "outsiders": outsiders,
        "labels": labels,
        "fixup": fixup,
        "map": mapping,
    }
    db = connect()
    match sys.argv[1:]:
        case ["apply"]:
            apply(db, None)
        case ["apply", count]:
            apply(db, int(count))
        case [name] if name in commands:
            commands[name](db)
        case _:
            sys.exit(f"usage: migrate.py {{{'|'.join(commands)}|apply [COUNT]}}")


main()
