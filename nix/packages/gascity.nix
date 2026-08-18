{ pkgs
, version
, revision
, source
}:

pkgs.stdenvNoCC.mkDerivation {
  pname = "gascity";
  inherit version;

  src = pkgs.fetchurl {
    url = "https://github.com/gastownhall/gascity/releases/download/v${version}/gascity_${version}_linux_amd64.tar.gz";
    hash = "sha256-jYyLUR2z/ESTFEWqtcufISUJwIZxBciA1sPQ5uXTPkI=";
  };

  sourceRoot = ".";
  dontConfigure = true;
  dontBuild = true;

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    install -m755 gc "$out/bin/gc"
    runHook postInstall
  '';

  meta = {
    description = "Gas City supervisor and workflow engine";
    homepage = "https://github.com/gastownhall/gascity";
    license = pkgs.lib.licenses.mit;
    mainProgram = "gc";
    platforms = [ "x86_64-linux" ];
  };

  passthru = {
    inherit revision source;
  };
}
