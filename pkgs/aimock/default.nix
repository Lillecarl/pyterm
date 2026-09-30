# The mock model API the agent CLIs are driven against: one local port that
# answers the Anthropic Messages API, the OpenAI Chat Completions API and the
# OpenAI Responses API, so `claude`, `codex` and `opencode` run without a
# provider and without a token. `nix/agents/README.md` is how each is aimed
# here, and `nix/agents/fixtures` is what it answers.
#
# Upstream ships the npm tarball already built and with no runtime
# dependencies, so there is nothing to compile: unpack it, put the tree where
# node resolves the package by name, and wrap the two bins at the node that
# runs them.
{
  lib,
  stdenvNoCC,
  nodejs,
  fetchurl,
  makeWrapper,
}:

stdenvNoCC.mkDerivation (finalAttrs: {
  pname = "aimock";
  version = "1.43.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/@copilotkit/aimock/-/aimock-${finalAttrs.version}.tgz";
    hash = "sha256-VPS6TvmEaWVX6EF21sTzcVAEeBmk7aN0hQo5BTS78Rc=";
  };

  nativeBuildInputs = [ makeWrapper ];

  dontBuild = true;

  installPhase = ''
    runHook preInstall

    package="$out/lib/node_modules/@copilotkit/aimock"
    mkdir -p "$(dirname "$package")"
    cp -r . "$package"

    mkdir -p "$out/bin"
    makeWrapper ${lib.getExe nodejs} "$out/bin/aimock" \
      --add-flags "$package/dist/aimock-cli.js"
    makeWrapper ${lib.getExe nodejs} "$out/bin/llmock" \
      --add-flags "$package/dist/cli.js"

    runHook postInstall
  '';

  meta = {
    description = "Mock OpenAI, Anthropic and other LLM APIs for deterministic tests";
    homepage = "https://github.com/CopilotKit/aimock";
    license = lib.licenses.mit;
    mainProgram = "aimock";
    platforms = lib.platforms.all;
  };
})
