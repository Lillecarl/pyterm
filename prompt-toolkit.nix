# What prompt-toolkit's own CI runs, and a stricter typing pass, as
# programs instead of sandbox verdicts. Upstream cannot take developer
# tooling for one person's fork, so it lives here and not there.
{
  writeShellApplication,
  ruff,
  typos,
  mypy,
  pyrefly,
  jujutsu,
  git,
  gh,
  devEnv,
}:
rec {
  /**
    What prompt-toolkit's own CI runs, against the working copy.

    The checks in `default.nix` judge locked revisions; this judges
    uncommitted edits, which is what needs judging before a commit.
    Run it in the prompt-toolkit checkout (or name it): `nix run
    --file . prompt-toolkit-ci`. Check out what is under test first:
    jj shows one tree at a time, so a send branch checks the branch
    and the merge checks everything.

    # Inputs

    `PROMPT_TOOLKIT_TESTS`
    : What pytest runs. The same knob the unit gate honors.

    `PROMPT_TOOLKIT_MYPY_VERSIONS`
    : The interpreters mypy checks, as CI matrices them. Defaults to
      the whole CI list.

    `PROMPT_TOOLKIT_MYPY_PLATFORMS`
    : The platforms mypy checks: `win32 linux darwin`, as CI runs
      them. Narrow it for a quick loop.

    # Notes

    Plain pytest, not `coverage run`: the gate runs it the same way,
    and coverage here feeds no codecov. One interpreter locally --
    the dev shell's -- where CI matrices six; the matrix stays in CI.
    Tool versions are the collection's, not uv-latest, so a version
    sensitive complaint can still differ there. One does today:
    this mypy flags a pre-existing `trace_dispatch` override in
    `application.py` that CI's mypy accepts. Nothing our branches
    touch is involved.
  */
  prompt-toolkit-ci = writeShellApplication {
    name = "prompt-toolkit-ci";
    runtimeInputs = [
      devEnv
      ruff
      typos
      mypy
    ];
    text = ''
      set -euo pipefail

      dir="''${1:-.}"
      cd "$dir"
      for f in pyproject.toml src tests; do
        if [ ! -e "$f" ]; then
          echo "prompt-toolkit-ci: no $f here -- run it in the prompt-toolkit checkout (or name it)" >&2
          exit 1
        fi
      done

      # The venv the suites run on. Its own prompt_toolkit is the
      # locked revision, so the working copy shadows it here and the
      # dependencies still resolve where the suites resolve them.
      # Replaced, not extended: anything older on it would shadow
      # nothing and confuse everything.
      export PYTHONPATH="src"
      export MYPYPATH="src"

      # Tool caches live outside the tree: a `.mypy_cache` beside
      # the sources would litter every working copy that runs this.
      cache_home="''${XDG_CACHE_HOME:-$HOME/.cache}/prompt-toolkit-ci"
      mkdir -p "$cache_home"
      export MYPY_CACHE_DIR="$cache_home/mypy"
      export RUFF_CACHE_DIR="$cache_home/ruff"

      # The knob is a word list on purpose.
      # shellcheck disable=SC2086
      python -m pytest ''${PROMPT_TOOLKIT_TESTS:-tests/}

      ruff check .
      ruff format --check .
      typos .

      interpreter="$(command -v python)"
      # Matrices are word lists on purpose.
      # shellcheck disable=SC2086
      for version in ''${PROMPT_TOOLKIT_MYPY_VERSIONS:-3.10 3.11 3.12 3.13 3.14}; do
        for platform in ''${PROMPT_TOOLKIT_MYPY_PLATFORMS:-win32 linux darwin}; do
          echo "mypy --strict src/ --python-version $version --platform $platform"
          mypy --strict src/ --python-version "$version" --platform "$platform" \
            --python-executable "$interpreter"
        done
      done
    '';
  };

  /**
    Pyrefly over the Python files this work changed, and only those.

    mypy --strict holds the tree; pyrefly is stricter and more often
    right, but running it over all of upstream would judge upstream's
    files too. This scopes it to the delta, which is the code with
    something to prove. `nix run --file . prompt-toolkit-pyrefly`,
    in the prompt-toolkit checkout.

    # Inputs

    `PYREFLY_FROM`
    : The revision the delta is measured from. Defaults to the
      upstream release this work builds on; move it when the floor
      moves. Ignored when `PYREFLY_FILES` names the files.

    `PYREFLY_FILES`
    : An explicit newline-separated file list to check, relative to
      the directory under test. The review harness names the PR's
      files itself, which also works where there is no jj to ask --
      a plain clone, where `jj diff` has nothing to say.
  */
  prompt-toolkit-pyrefly = writeShellApplication {
    name = "prompt-toolkit-pyrefly";
    runtimeInputs = [
      devEnv
      pyrefly
      jujutsu
    ];
    text = ''
      set -euo pipefail

      dir="''${1:-.}"
      cd "$dir"

      files=()
      if [ -n "''${PYREFLY_FILES:-}" ]; then
        while IFS= read -r f || [ -n "$f" ]; do
          if [ -n "$f" ] && [ -f "$f" ]; then
            files+=("$f")
          fi
        done <<< "''${PYREFLY_FILES}"
      else
        from="''${PYREFLY_FROM:-upstream-3.0.53}"

        # What changed since the base: adds and moves, Python only. The
        # assignment is outside the pipeline so a bad revision fails
        # here instead of reading as no changes.
        summary="$(jj diff --from "$from" --to @ --summary)"
        mapfile -t changed < <(printf '%s\n' "$summary" \
          | sed -n -e 's/^M //p' -e 's/^A //p' -e 's/^R .* -> //p' \
          | grep '\.py$' || true)

        for f in "''${changed[@]}"; do
          if [ -f "$f" ]; then
            files+=("$f")
          fi
        done
      fi

      if [ "''${#files[@]}" -eq 0 ]; then
        echo "prompt-toolkit-pyrefly: no Python files to check"
        exit 0
      fi

      # The interpreter flag points pyrefly at the same site-packages
      # the suites run on, the way the pymux types check does.
      pyrefly check --preset default \
        --python-interpreter-path "$(command -v python)" \
        "''${files[@]}"
    '';
  };

  /**
    Evidence for reviewing one upstream PR, base against head.

    Fetches the PR into a throwaway sandbox -- a plain git clone,
    never the umbrella checkout -- builds one worktree per side, and
    runs the same verdicts on both: `prompt-toolkit-ci` whole, and
    `prompt-toolkit-pyrefly` over the PR's own Python files. Reports
    only the delta, because anything failing on base is not the
    author's bug, and appends the run to a findings file the reviewer
    finishes by hand. Judgment stays human; this only gathers facts.

    `nix run --file . prompt-toolkit-review -- 2118` reviews that PR
    in `~/Code/pt-review`. It never posts, never pushes, and refuses
    a sandbox whose push URL is not disabled or whose origin is not
    upstream -- running it in the wrong checkout fails closed.

    # Inputs

    `PT_REVIEW_NOTES`
    : Where findings files go. Defaults to `~/Code/pt-review-notes`.

    `--full`
    : Third argument. Runs the whole mypy version/platform matrix
      instead of one combo. The default single combo (newest
      interpreter, linux) is the fast loop; the matrix stays opt-in
      because it multiplies minutes by sides.

    `PROMPT_TOOLKIT_TESTS`
    : Passed through, so a rerun can narrow pytest the same way the
      CI app narrows it.
  */
  prompt-toolkit-review = writeShellApplication {
    name = "prompt-toolkit-review";
    runtimeInputs = [
      prompt-toolkit-ci
      prompt-toolkit-pyrefly
      devEnv
      git
      gh
    ];
    text = ''
      set -euo pipefail

      pr="''${1:-}"
      sandbox="''${2:-$HOME/Code/pt-review}"
      mode="''${3:-}"
      notes_dir="''${PT_REVIEW_NOTES:-$HOME/Code/pt-review-notes}"

      if ! [[ "$pr" =~ ^[0-9]+$ ]]; then
        echo "usage: prompt-toolkit-review PR-NUMBER [sandbox-dir] [--full]" >&2
        exit 1
      fi
      full=0
      if [ "$mode" = "--full" ]; then
        full=1
      fi

      cd "$sandbox"
      if [ ! -d .git ]; then
        echo "prompt-toolkit-review: no .git in $sandbox -- point it at the review sandbox" >&2
        exit 1
      fi
      origin_url="$(git remote get-url origin)"
      case "$origin_url" in
      *jonathanslenders/python-prompt-toolkit*) ;;
      *)
        echo "prompt-toolkit-review: origin is $origin_url, not upstream -- refusing" >&2
        exit 1
        ;;
      esac
      push_url="$(git remote get-url --push origin)"
      case "$push_url" in
      *no-push*) ;;
      *)
        echo "prompt-toolkit-review: push URL is live -- disable it first:" >&2
        echo "  git -C $sandbox remote set-url --push origin no-push" >&2
        exit 1
        ;;
      esac

      # One parse: title, author, url, base branch. Values travel in
      # printf arguments from here on, never through eval, because a
      # PR title is somebody else's string.
      meta="$(gh pr view "$pr" --repo jonathanslenders/python-prompt-toolkit \
        --json title,author,url,baseRefName)"
      # shellcheck disable=SC2034
      IFS=$'\x1f' read -r title author url base_branch < <(printf '%s' "$meta" \
        | python -c 'import json,sys; m = json.load(sys.stdin); print(m["title"], m["author"]["login"], m["url"], m["baseRefName"], sep="\x1f")')

      git fetch origin "pull/$pr/head:pr/$pr"
      git fetch origin "$base_branch"
      base="$(git merge-base "pr/$pr" "origin/$base_branch")"
      head_rev="$(git rev-parse "pr/$pr")"

      # Worktrees stay put after the run: probing continues where the
      # harness stops. Rebuilt only when the PR moved underneath.
      wt_base="$sandbox/.wt-$pr-base"
      wt_head="$sandbox/.wt-$pr-head"
      ensure_wt() {
        local wt="$1" rev="$2"
        if git worktree list --porcelain | grep -qF "worktree $wt"; then
          if [ "$(git -C "$wt" rev-parse HEAD)" != "$rev" ]; then
            git worktree remove --force "$wt"
            git worktree add --detach "$wt" "$rev"
          fi
        else
          git worktree add --detach "$wt" "$rev"
        fi
      }
      ensure_wt "$wt_base" "$base"
      ensure_wt "$wt_head" "$head_rev"

      # The diff exits 1 when there is one, which is the normal case.
      py_files="$(git diff --name-only "$base" "$head_rev" -- '*.py' || true)"

      workdir="$sandbox/.run-$pr"
      mkdir -p "$workdir"

      # Runs both verdicts on one side and records the codes. Every
      # failure is captured, so this always returns 0 itself.
      run_side() {
        local wt="$1" tag="$2"
        local ci_rc=0 py_rc=0
        (
          cd "$wt" || exit 1
          export XDG_CACHE_HOME="$workdir/cache-$tag"
          if [ "$full" -eq 0 ]; then
            export PROMPT_TOOLKIT_MYPY_VERSIONS="3.14"
            export PROMPT_TOOLKIT_MYPY_PLATFORMS="linux"
          fi
          prompt-toolkit-ci >"$workdir/ci-$tag.log" 2>&1
        ) || ci_rc=$?
        local side_files=""
        side_files="$(printf '%s\n' "$py_files" | while IFS= read -r f || [ -n "$f" ]; do
          if [ -n "$f" ] && [ -e "$wt/$f" ]; then printf '%s\n' "$f"; fi
        done || true)"
        (
          cd "$wt" || exit 1
          export XDG_CACHE_HOME="$workdir/cache-$tag"
          if [ -n "$side_files" ]; then
            PYREFLY_FILES="$side_files" prompt-toolkit-pyrefly "$wt" >"$workdir/pyrefly-$tag.log" 2>&1
          else
            printf '%s\n' "prompt-toolkit-review: no Python files present on $tag side" >"$workdir/pyrefly-$tag.log"
          fi
        ) || py_rc=$?
        printf '%s %s\n' "$ci_rc" "$py_rc" >"$workdir/rc-$tag"
      }
      run_side "$wt_base" base
      run_side "$wt_head" head
      # shellcheck disable=SC2034
      read -r ci_base py_base <"$workdir/rc-base"
      # shellcheck disable=SC2034
      read -r ci_head py_head <"$workdir/rc-head"

      fails_base="$(grep -h '^FAILED ' "$workdir/ci-base.log" | sort -u || true)"
      fails_head="$(grep -h '^FAILED ' "$workdir/ci-head.log" | sort -u || true)"
      new_fails="$(comm -13 <(printf '%s\n' "$fails_base") <(printf '%s\n' "$fails_head") || true)"
      fixed_fails="$(comm -23 <(printf '%s\n' "$fails_base") <(printf '%s\n' "$fails_head") || true)"
      upstream_checks="$(gh pr checks "$pr" --repo jonathanslenders/python-prompt-toolkit || true)"

      slug="$(printf '%s' "$title" | tr '[:upper:]' '[:lower:]' | tr -c '[:alnum:]' '-' | tr -s '-' | cut -c1-40 | sed 's/-$//')"
      note="$notes_dir/$pr-$slug.md"
      mkdir -p "$notes_dir"
      if [ ! -e "$note" ]; then
        {
          printf '# Review: #%s %s\n' "$pr" "$title"
          printf '# %s by %s, base %s\n' "$url" "$author" "$base_branch"
          printf '\n## Claim\n\n## Probes\n\n## Suggested tests\n\n## Draft review\n'
        } >"$note"
      fi
      {
        printf '\n## Run %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        printf 'base %s head %s matrix %s\n' "$base" "$head_rev" "$([ "$full" -eq 1 ] && printf full || printf single)"
        printf 'ci: base=%s head=%s pyrefly: base=%s head=%s\n' "$ci_base" "$ci_head" "$py_base" "$py_head"
        printf '\nPython files in the PR:\n%s\n' "$py_files"
        printf '\nFailing tests, base:\n%s\n' "$fails_base"
        printf '\nFailing tests, head:\n%s\n' "$fails_head"
        printf '\nNew failures on head:\n%s\n' "$new_fails"
        printf '\nFixed on head:\n%s\n' "$fixed_fails"
        printf '\nUpstream checks:\n%s\n' "$upstream_checks"
        printf '\nLogs: %s/ci-base.log ci-head.log pyrefly-base.log pyrefly-head.log\n' "$workdir"
      } >>"$note"

      printf 'PR #%s %s by %s\n' "$pr" "$title" "$author"
      printf 'ci: base=%s head=%s pyrefly: base=%s head=%s\n' "$ci_base" "$ci_head" "$py_base" "$py_head"
      if [ -n "$new_fails" ]; then
        printf 'new failures:\n%s\n' "$new_fails"
      fi
      printf 'notes: %s\nworktrees: %s %s\n' "$note" "$wt_base" "$wt_head"
      printf 'remove worktrees with:\n  git -C %s worktree remove --force .wt-%s-base\n  git -C %s worktree remove --force .wt-%s-head\n' "$sandbox" "$pr" "$sandbox" "$pr"
    '';
  };
}
