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
    install -m 0755 ${../../scripts/publish-pr.py} \
      "$out/share/d2b-gascity/scripts/publish-pr.py"
    install -m 0755 ${../../scripts/publication-worker.py} \
      "$out/share/d2b-gascity/scripts/publication-worker.py"
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

  publishPrWrapper = pkgs.writeShellScriptBin
    "d2b-gascity-publish-pr" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/publish-pr.py" "$@"
  '';

  publicationWorkerWrapper = pkgs.writeShellScriptBin
    "d2b-gascity-publication-worker" ''
    export D2B_GASCITY_ROOT="${portableAssets}/share/d2b-gascity"
    exec ${pkgs.python3}/bin/python3 \
      "$D2B_GASCITY_ROOT/scripts/publication-worker.py" "$@"
  '';

  publicationWorker = pkgs.symlinkJoin {
    name = "d2b-gascity-publication-worker";
    paths = [
      publicationWorkerWrapper
      publishPrWrapper
    ];
  };

  runtimePackages = [
    gascity
    beads
    dolt
    copilot
    go
    pkgs.git
    pkgs.gh
    pkgs.python3
    pkgs.jq
    pkgs.tmux
    pkgs.lsof
    pkgs.procps
    pkgs.cacert
    pkgs.openssl
    tinyauth
    nginx
    pkgs.util-linux
    pkgs.iproute2
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
    publicationWorker
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
      discordImportWrapper
      publishPrWrapper
      publicationWorkerWrapper
      publicationWorker;
  };
  meta = {
    description = "Pinned Gas City contributor runtime closure";
    platforms = pkgs.lib.platforms.linux;
  };
}
