{ pkgs
, gascity
, beads
, dolt
, copilot
, go
, tinyauth
, nginx
, sourceManifest
}:

let
  portableAssets = pkgs.runCommand "d2b-gascity-portable-assets" {
    nativeBuildInputs = [ pkgs.coreutils ];
  } ''
    set -euo pipefail
    mkdir -p "$out/share/d2b-gascity/city" "$out/share/d2b-gascity/scripts"
    cp -R ${../../city}/. "$out/share/d2b-gascity/city/"
    install -m 0755 ${../../scripts/bootstrap.py} \
      "$out/share/d2b-gascity/scripts/bootstrap.py"
    install -m 0755 ${../../scripts/operator.py} \
      "$out/share/d2b-gascity/scripts/operator.py"
    install -m 0755 ${../../scripts/copilot-provider.py} \
      "$out/share/d2b-gascity/scripts/copilot-provider.py"
    install -m 0755 ${../../scripts/discord-import.py} \
      "$out/share/d2b-gascity/scripts/discord-import.py"
  '';

  bootstrapWrapper = pkgs.writeShellScriptBin "d2b-gascity-bootstrap" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/bootstrap.py" "$@"
  '';

  operatorWrapper = pkgs.writeShellScriptBin "d2b-gascity-operator" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/operator.py" "$@"
  '';

  copilotProviderWrapper = pkgs.writeShellScriptBin
    "d2b-gascity-copilot-provider" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/copilot-provider.py" "$@"
  '';

  discordImportWrapper = pkgs.writeShellScriptBin
    "d2b-gascity-discord-import" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/discord-import.py" "$@"
  '';

  runtimePackages = [
    gascity
    beads
    dolt
    copilot
    go
    pkgs.git
    pkgs.gh
    pkgs.python3
    pkgs.cacert
    tinyauth
    nginx
  ];

  runtimeEnvironment = pkgs.buildEnv {
    name = "gas-city-contributor-runtime";
    paths = runtimePackages;
    pathsToLink = [
      "/bin"
      "/etc/ssl/certs"
    ];
    ignoreCollisions = true;
  };
in
pkgs.symlinkJoin {
  name = "gas-city-contributor";
  paths = [
    runtimeEnvironment
    sourceManifest
    portableAssets
    bootstrapWrapper
    operatorWrapper
    copilotProviderWrapper
    discordImportWrapper
  ];
  passthru = {
    inherit
      gascity
      beads
      dolt
      copilot
      go
      tinyauth
      nginx
      runtimePackages
      runtimeEnvironment
      sourceManifest
      portableAssets
      bootstrapWrapper
      operatorWrapper
      copilotProviderWrapper
      discordImportWrapper;
  };
  meta = {
    description = "Pinned Gas City contributor runtime closure";
    platforms = pkgs.lib.platforms.linux;
  };
}
