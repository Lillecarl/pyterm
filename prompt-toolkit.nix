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
  devEnv,
}:
{
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
      moves.
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
      from="''${PYREFLY_FROM:-upstream-3.0.53}"

      # What changed since the base: adds and moves, Python only. The
      # assignment is outside the pipeline so a bad revision fails
      # here instead of reading as no changes.
      summary="$(jj diff --from "$from" --to @ --summary)"
      mapfile -t changed < <(printf '%s\n' "$summary" \
        | sed -n -e 's/^M //p' -e 's/^A //p' -e 's/^R .* -> //p' \
        | grep '\.py$' || true)

      files=()
      for f in "''${changed[@]}"; do
        if [ -f "$f" ]; then
          files+=("$f")
        fi
      done

      if [ "''${#files[@]}" -eq 0 ]; then
        echo "prompt-toolkit-pyrefly: no Python files changed since $from"
        exit 0
      fi

      # The interpreter flag points pyrefly at the same site-packages
      # the suites run on, the way the pymux types check does.
      pyrefly check --preset default \
        --python-interpreter-path "$(command -v python)" \
        "''${files[@]}"
    '';
  };
}
