#!/usr/bin/env bash
# Export each source of this tree to its own repository, through josh.
# The workflow `josh-export.yml` runs it, and so can a person, from a
# checkout with the whole history. Lillecarl/pymux#667.
#
#   .github/josh-export.sh <rev> [--push]
#
# Per source: filter <rev> through ':/<src>', which gives the source's own
# commits back with their own hashes. Refuse unless the source's `main`
# exists and is an ancestor of the export, and the target branch is absent
# or one too: the push is never forced, and nothing here rewrites what a
# repository already holds. Without --push, report only.
#
# JOSH_REMOTE is the URL of a source with %s for its name, and JOSH_BRANCH
# the branch to push to, `main` unless named. josh-filter must be on PATH,
# and at the version the workflow pins: another version may filter to
# other hashes.
set -euo pipefail
REV=${1:?usage: josh-export.sh <rev> [--push]}
PUSH=${2:-}
REMOTE=${JOSH_REMOTE:-git@github.com:Lillecarl/%s.git}
TARGET=${JOSH_BRANCH:-main}
SOURCES=(pyte ptyhost ptterm txterm pymux pysmithay pyterm-pytest)

commit=$(git rev-parse "$REV^{commit}")
echo "exporting $commit to the $TARGET branches"

# Whether $1 is an ancestor of $2 that this repository holds.
behind() {
  git cat-file -e "$1^{commit}" 2>/dev/null && git merge-base --is-ancestor "$1" "$2"
}

failed=0
for src in "${SOURCES[@]}"; do
  # shellcheck disable=SC2059
  url=$(printf "$REMOTE" "$src")
  # Not under refs/heads, so jj does not take it for a bookmark.
  ref=refs/josh-export/$src
  josh-filter ":/$src" "$commit" --update "$ref" >/dev/null
  exported=$(git rev-parse "$ref")
  remote_main=$(git ls-remote "$url" refs/heads/main | cut -f1)
  remote_target=$(git ls-remote "$url" "refs/heads/$TARGET" | cut -f1)
  if [[ -z $remote_main ]]; then
    verdict="REFUSED: no main"
  elif ! behind "$remote_main" "$exported"; then
    verdict="REFUSED: main is not behind the export; import it again"
  elif [[ -n $remote_target ]] && ! behind "$remote_target" "$exported"; then
    verdict="REFUSED: $TARGET is not behind the export"
  else
    verdict=ok
  fi
  echo "$src: export ${exported:0:12}, main ${remote_main:0:12}, $TARGET ${remote_target:0:12}: $verdict"
  if [[ $verdict != ok ]]; then
    failed=1
  elif [[ $PUSH == --push && $exported != "$remote_target" ]]; then
    git push "$url" "$exported:refs/heads/$TARGET"
  fi
done
exit $failed
