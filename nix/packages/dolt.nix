{ pkgs
, source
, buildGoModule ? pkgs.buildGoModule
}:

buildGoModule rec {
  pname = "dolt";
  version = "2.1.7";
  src = source;

  modRoot = "./go";
  subPackages = [ "cmd/dolt" ];
  vendorHash = "sha256-l0SHq3WTajqGTE5sV6RgLgVLS+i7AhAxfJkJmAvv2ok=";
  proxyVendor = true;
  doCheck = false;

  env.CGO_ENABLED = "1";
  env.GOTOOLCHAIN = "local";
  buildInputs = [ pkgs.icu ];

  meta = {
    description = "Relational database with version control and a Git-like CLI";
    homepage = "https://www.dolthub.com/";
    license = pkgs.lib.licenses.asl20;
    mainProgram = "dolt";
    platforms = pkgs.lib.platforms.linux;
  };

  passthru = {
    sourceRepository = "dolthub/dolt";
  };
}
