{ pkgs
, source
, buildGoModule ? pkgs.buildGoModule
, revision
}:

buildGoModule rec {
  pname = "gascity";
  version = "0-unstable-2026-08-14";
  src = source;
  patches = [
    ../patches/gascity-acp-session-identity.patch
  ];

  subPackages = [ "cmd/gc" ];
  vendorHash = "sha256-05Ch0dn0W8OKZaGFq04VQS7QzLkgo//chz0WBjjefrQ=";
  proxyVendor = true;

  env.CGO_ENABLED = "0";
  env.GOTOOLCHAIN = "local";

  nativeCheckInputs = [
    pkgs.bash
    pkgs.coreutils
    pkgs.git
    pkgs.gnumake
    pkgs.jq
    pkgs.python3
    pkgs.procps
  ];

  postPatch = ''
    patchShebangs scripts
  '';

  ldflags = [
    "-s"
    "-w"
    "-X main.version=${version}"
    "-X main.commit=${revision}"
    "-X main.date=unknown"
  ];

  preBuild = ''
    export GOFLAGS="''${GOFLAGS:-} -buildvcs=false"
  '';

  doCheck = true;
  checkPhase = ''
    runHook preCheck
    export HOME="$TMPDIR/home"
    mkdir -p "$HOME"
    go test -trimpath=false -count=1 \
      ./internal/config/... \
      ./internal/formula/... \
      ./internal/pidutil/... \
      ./internal/processgroup/... \
      ./internal/runtime/acp/... \
      ./internal/runtime/registry/... \
      ./internal/runtime/subprocess/... \
      ./internal/supervisor/... \
      ./internal/worker \
      ./scripts/cipolicy/...
    runHook postCheck
  '';

  meta = {
    description = "Gas City supervisor and workflow engine";
    homepage = "https://github.com/gastownhall/gascity";
    license = pkgs.lib.licenses.mit;
    mainProgram = "gc";
    platforms = pkgs.lib.platforms.linux;
  };

  passthru = {
    inherit revision;
  };
}
