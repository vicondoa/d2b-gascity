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
      sourceManifest;
  };
  meta = {
    description = "Pinned Gas City contributor runtime closure";
    platforms = pkgs.lib.platforms.linux;
  };
}
