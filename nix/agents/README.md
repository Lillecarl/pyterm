# A mock model API for the agent CLIs

The coding agents this collection is tested against -- `claude`, `codex` and
`opencode` -- each read a model base URL from the environment or a config
file. `aimock` answers that URL on a local port, so a run costs no token and
needs no network. `pkgs/aimock/default.nix` holds the package, and the dev
shell puts `aimock` and `llmock` on PATH.

It speaks three wire formats on one port: the Anthropic Messages API at
`/v1/messages` (what `claude` and `opencode` use), the OpenAI Responses API at
`/v1/responses` (what `codex` uses), and the OpenAI Chat Completions API at
`/v1/chat/completions`.

## Start it

    llmock -p 4010 -f nix/agents/fixtures

The two fixtures beside this file:

- `hello.json` answers a message that holds `hello`.
- `scroll.json` answers a message that holds `scroll` with sixty lines,
  streaming at 60 tokens a second. This is the one that makes a screen scroll.

A fixture matches the last user message, so the prompt picks the reply. Add
`--validate-on-load` to fail at startup on a malformed fixture, or lint them
without starting the server:

    aimock validate nix/agents/fixtures

## claude

    ANTHROPIC_BASE_URL=http://127.0.0.1:4010 \
    ANTHROPIC_AUTH_TOKEN=mock ANTHROPIC_API_KEY= \
    ANTHROPIC_MODEL=claude-sonnet-4-6 \
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
    claude

The base URL carries no `/v1`, because Claude Code appends `/v1/messages`
itself. Set `ANTHROPIC_AUTH_TOKEN` and leave `ANTHROPIC_API_KEY` empty, or
Claude Code may fall back to Anthropic auth. The mock ignores the model name;
use one this Claude Code version knows, or it warns about the catalog.

## codex

`codex` reads providers from `$CODEX_HOME/config.toml`. Point it at a copy of
the sample:

    scratch="$HOME/.cache/pyterm-codex"
    mkdir -p "$scratch"
    cp nix/agents/codex.config.toml "$scratch/config.toml"
    CODEX_HOME="$scratch" PROBE_API_KEY=mock \
      codex exec --skip-git-repo-check "say hi"

`codex` speaks only the Responses API, so the provider sets
`wire_api = "responses"`.

## opencode

    OPENCODE_CONFIG=$PWD/nix/agents/opencode.json \
    OPENCODE_DISABLE_MODELS_FETCH=1 \
    opencode run "say hi"

The sample overrides the built-in `anthropic` provider's base URL and adds a
model named `claude-probe`. `opencode` also reaches the OpenAI formats if you
give it a provider that uses them.

## Record one real run, then replay it forever

When a fixture is not faithful enough, record a real session once and replay
the tape without a provider afterwards:

    llmock --record --provider-anthropic https://api.anthropic.com \
      -f nix/agents/fixtures

The recorded fixtures land in the `-f` directory. Replaying uses the recorded
inter-frame timing, so a scroll test reproduces the pace of the real stream.
`--replay-speed 2` doubles it.
