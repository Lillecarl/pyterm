# The mock and its fixtures, judged without an agent: the server comes up and
# each of the three wire formats answers from a fixture. It is the gate under
# `nix/agents`; the agents themselves are run by hand, because their binaries
# are not this collection's to pin.
#
# `sources` reaches `nix/suite.nix` for the two-derivation shape every check
# here has. `aimock` carries both bins, and `llmock` is the one that takes
# `-f`.
{
  runCommand,
  sources,
  aimock,
  curl,
}:
let
  inherit (import "${sources.pyte}/nix/suite.nix" { inherit runCommand; }) suite;
in
suite {
  name = "aimock-fixtures";
  inputs = [
    aimock
    curl
  ];
} ''
  llmock -p 4010 -f ${./fixtures} --log-level warn &
  server="$!"
  trap 'kill "$server" 2>/dev/null || true' EXIT

  ready=0
  for _ in $(seq 1 100); do
    if curl -sf http://127.0.0.1:4010/health >/dev/null; then
      ready=1
      break
    fi
    sleep 0.1
  done
  if [ "$ready" != 1 ]; then
    echo "the mock never answered on 127.0.0.1:4010"
    exit 1
  fi

  post() {
    curl -sf -X POST "http://127.0.0.1:4010$1" \
      -H 'content-type: application/json' -d "$2"
  }

  # The Anthropic Messages route, what claude and opencode use.
  post /v1/messages \
    '{"model":"probe","max_tokens":16,"messages":[{"role":"user","content":"hello"}]}' \
    | grep -q "Hello from aimock"

  # The OpenAI Responses route, what codex uses.
  post /v1/responses \
    '{"model":"probe","input":[{"role":"user","content":[{"type":"input_text","text":"hello"}]}]}' \
    | grep -q "Hello from aimock"

  # The OpenAI Chat Completions route.
  post /v1/chat/completions \
    '{"model":"probe","messages":[{"role":"user","content":"hello"}]}' \
    | grep -q "Hello from aimock"

  echo "every wire format answered from the fixtures"
''
