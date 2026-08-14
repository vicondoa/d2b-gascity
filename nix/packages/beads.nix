{ pkgs
, source
, buildGoModule ? pkgs.buildGoModule
, revision
}:

buildGoModule rec {
  pname = "beads";
  version = "1.1.1-unstable-20260805";
  src = source;

  subPackages = [ "cmd/bd" ];
  tags = [ "gms_pure_go" ];
  vendorHash = "sha256-CW+ba1KYpmBZ1UXHCr2B/EHOr8LDi494BuEDGHABLbk=";
  proxyVendor = true;
  doCheck = false;

  env.CGO_ENABLED = "1";
  env.GOTOOLCHAIN = "local";
  buildInputs = [ pkgs.icu ];

  ldflags = [
    "-X main.Version=${version}"
    "-X main.Build=${revision}"
    "-X main.Commit=${revision}"
  ];

  meta = {
    description = "Issue tracker designed for AI-supervised coding workflows";
    homepage = "https://github.com/steveyegge/beads";
    license = pkgs.lib.licenses.mit;
    mainProgram = "bd";
    platforms = pkgs.lib.platforms.linux;
  };

  passthru = {
    inherit revision;
    sourceRepository = "steveyegge/beads";
  };
}
