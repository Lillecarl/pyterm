#!/usr/bin/env bash
# Export each source of this tree to its own repository, through josh.
# The workflow `josh-export.yml` runs it, and so can a person, from a
# checkout with the whole history. Lillecarl/pymux#667.
#
#   .github/josh-export.sh <rev> [--push]
#
# Per source: filter <rev> through ':/<src>', which gives the source's own
# commits back with their own hashes. Refuse unless the source's default
# branch and the target branch are both absent or ancestors of the export:
# the push is never forced, and nothing here rewrites what a repository
# already holds. Without --push, report only.
#
# JOSH_REMOTE is the URL of a source with %s for its name, and JOSH_BRANCH
# the branch to push to; `default` is each source's own default branch. josh-filter must be on PATH, and at the version the
# workflow pins: another version may filter to other hashes.
set -euo pipefail
REV=${1:?usage: josh-export.sh <rev> [--push]}
PUSH=${2:-}
REMOTE=${JOSH_REMOTE:-git@github.com:Lillecarl/%s.git}
TARGET=${JOSH_BRANCH:-josh}
declare -A DEFAULT_BRANCH=(
  [pyte]=master
  [ptyhost]=main
  [ptterm]=master
  [txterm]=main
  [pymux]=master
  [pysmithay]=main
  [pyterm-pytest]=main
)

commit=$(git rev-parse "$REV^{commit}")
echo "exporting $commit to the $TARGET branches"

# Whether $1 is empty or an ancestor of $2 that this repository holds.
behind() {
  [[ -z $1 ]] || { git cat-file -e "$1^{commit}" 2>/dev/null && git merge-base --is-ancestor "$1" "$2"; }
}

failed=0
for src in "${!DEFAULT_BRANCH[@]}"; do
  # shellcheck disable=SC2059
  url=$(printf "$REMOTE" "$src")
  default=${DEFAULT_BRANCH[$src]}
  target=$TARGET
  [[ $target == default ]] && target=$default
  # Not under refs/heads, so jj does not take it for a bookmark.
  ref=refs/josh-export/$src
  josh-filter ":/$src" "$commit" --update "$ref" >/dev/null
  exported=$(git rev-parse "$ref")
  remote_default=$(git ls-remote "$url" "refs/heads/$default" | cut -f1)
  remote_target=$(git ls-remote "$url" "refs/heads/$target" | cut -f1)
  if ! behind "$remote_default" "$exported"; then
    verdict="REFUSED: $default is not behind the export; import it again"
  elif ! behind "$remote_target" "$exported"; then
    verdict="REFUSED: $target is not behind the export"
  else
    verdict=ok
  fi
  echo "$src: export ${exported:0:12}, $default ${remote_default:0:12}, $target ${remote_target:0:12}: $verdict"
  if [[ $verdict != ok ]]; then
    failed=1
  elif [[ $PUSH == --push && $exported != "$remote_target" ]]; then
    git push "$url" "$exported:refs/heads/$target"
  fi
done
exit $failed
