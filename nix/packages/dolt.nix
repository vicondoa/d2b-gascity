{ pkgs
, version
, source
}:

pkgs.stdenvNoCC.mkDerivation {
  pname = "dolt";
  inherit version;

  src = pkgs.fetchurl {
    url = "https://github.com/dolthub/dolt/releases/download/v${version}/dolt-linux-amd64.tar.gz";
    hash = "sha256-FZg+gRNB7ZTl1H+/xB0vV9jHqmXu5RHSWjw/1Ud+KOc=";
  };

  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    install -m755 bin/dolt "$out/bin/dolt"
    runHook postInstall
  '';

  meta = {
    description = "Relational database with version control and a Git-like CLI";
    homepage = "https://www.dolthub.com/";
    license = pkgs.lib.licenses.asl20;
    mainProgram = "dolt";
    platforms = [ "x86_64-linux" ];
  };

  passthru = {
    inherit source;
    sourceRepository = "dolthub/dolt";
  };
}
