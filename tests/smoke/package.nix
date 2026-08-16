{ pkgs
, gasCityContributor
, gascityRevision
, gascityPacksRevision
, beadsRevision
, llmAgentsRevision
, doltVersion
, goVersion
, copilotVersion
, tinyauthVersion
, nginxVersion
}:

pkgs.runCommand "gas-city-package-smoke" {
  nativeBuildInputs = [
    pkgs.coreutils
    pkgs.gnugrep
    pkgs.jq
  ];
} ''
  set -euo pipefail

  export PATH="${gasCityContributor}/bin:${pkgs.coreutils}/bin:${pkgs.gnugrep}/bin:${pkgs.jq}/bin"
  export HOME="$TMPDIR/home"
  mkdir -p "$HOME"

  expectedGascityRevision="f6741d94861aa14f0253deffbe9efb1cb3a35d92"
  expectedGascityPacksRevision="5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe"
  expectedBeadsRevision="bf97b73749ac3ef2fca2365b54537ac041ad4293"
  expectedDoltVersion="2.1.7"
  expectedGoVersion="1.26.6"
  expectedCopilotVersion="1.0.79"
  expectedTinyAuthVersion="5.1.3"
  expectedNginxVersion="1.30.2"
  expectedLlmAgentsRevision="387989ee56d550d86d46d9458ad68a55b9e0ca3b"

  test "${gascityRevision}" = "$expectedGascityRevision"
  test "${gascityPacksRevision}" = "$expectedGascityPacksRevision"
  test "${beadsRevision}" = "$expectedBeadsRevision"
  test "${doltVersion}" = "$expectedDoltVersion"
  test "${goVersion}" = "$expectedGoVersion"
  test "${copilotVersion}" = "$expectedCopilotVersion"
  test "${tinyauthVersion}" = "$expectedTinyAuthVersion"
  test "${nginxVersion}" = "$expectedNginxVersion"
  test "${llmAgentsRevision}" = "$expectedLlmAgentsRevision"

  for tool in gc bd dolt git gh copilot python3 tinyauth nginx go \
    openssl jq tmux lsof pgrep flock unshare ip \
    d2b-gascity-copilot-provider d2b-gascity-discord-import \
    d2b-gascity-publish-pr d2b-gascity-publication-worker; do
    toolPath="${gasCityContributor}/bin/$tool"
    test -x "$toolPath"
    test "$(command -v "$tool")" = "$toolPath"
  done
  unshare --version >/dev/null
  ip -Version >/dev/null

  test -r "${gasCityContributor}/etc/ssl/certs/ca-bundle.crt"
  test ! -e "${gasCityContributor}/etc/nginx"
  test ! -e "${gasCityContributor}/share/gas-city-contributor/city"
  test ! -e "${gasCityContributor}/share/gas-city-contributor/dashboard"
  test -x "${gasCityContributor}/bin/d2b-gascity-bootstrap"
  test -x "${gasCityContributor}/bin/d2b-gascity-operator"
  test -x "${gasCityContributor}/bin/d2b-gascity-copilot-provider"
  test -x "${gasCityContributor}/bin/d2b-gascity-discord-import"
  test -x "${gasCityContributor}/bin/d2b-gascity-publish-pr"
  test -x "${gasCityContributor}/bin/d2b-gascity-publication-worker"
  test -r "${gasCityContributor}/share/d2b-gascity/city/city.toml"
  test -r "${gasCityContributor}/share/d2b-gascity/city/pack.toml"
  test -r "${gasCityContributor}/share/d2b-gascity/city/packs.lock"
  test -r "${gasCityContributor}/share/d2b-gascity/city/role-provider-matrix.json"
  test -r "${gasCityContributor}/share/d2b-gascity/city/worktree-producer-inventory.json"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/bootstrap.py"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/operator.py"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/copilot-provider.py"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/discord-import.py"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/publish-pr.py"
  test -x "${gasCityContributor}/share/d2b-gascity/scripts/publication-worker.py"
  test ! -e "${gasCityContributor}/share/d2b-gascity/dashboard"

  gcVersion="$(${gasCityContributor}/bin/gc version --long)"
  printf '%s\n' "$gcVersion" | grep -F "commit: $expectedGascityRevision"
  printf '%s\n' "$(${gasCityContributor}/bin/bd version)" \
    | grep -F "$expectedBeadsRevision"
  printf '%s\n' "$(${gasCityContributor}/bin/dolt version)" \
    | grep -F "$expectedDoltVersion"
  printf '%s\n' "$(${gasCityContributor}/bin/go version)" \
    | grep -F "go$expectedGoVersion"
  printf '%s\n' "$(${gasCityContributor}/bin/copilot --version)" \
    | grep -F "$expectedCopilotVersion"
  printf '%s\n' "$(${gasCityContributor}/bin/tinyauth version)" \
    | grep -F "$expectedTinyAuthVersion"
  printf '%s\n' "$(${gasCityContributor}/bin/nginx -v 2>&1)" \
    | grep -F "$expectedNginxVersion"

  manifest="${gasCityContributor}/share/gas-city-contributor/sources.json"
  test -r "$manifest"
  jq -e \
    --arg gascity "${gascityRevision}" \
    --arg gascityPacks "${gascityPacksRevision}" \
    --arg beads "${beadsRevision}" \
    --arg llmAgents "${llmAgentsRevision}" \
    --arg dolt "${doltVersion}" \
    --arg go "${goVersion}" \
    --arg copilot "${copilotVersion}" \
    --arg tinyauth "${tinyauthVersion}" \
    --arg nginx "${nginxVersion}" \
    '.schemaVersion == 1
     and .inputs.gascity.revision == $gascity
     and .inputs.gascityPacks.revision == $gascityPacks
     and .inputs.beads.revision == $beads
     and .inputs.llmAgents.revision == $llmAgents
     and .packages.dolt.version == $dolt
     and .packages.go.version == $go
     and .packages.copilotCli.version == $copilot
     and .packages.tinyauth.version == $tinyauth
     and .packages.nginx.version == $nginx
     and .runtime.caBundle == "etc/ssl/certs/ca-bundle.crt"' \
    "$manifest" >/dev/null

  mkdir -p "$out"
  printf '%s\n' "gas-city-package-smoke: ok" > "$out/result"
''
