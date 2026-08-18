{ pkgs
, version
, revision
, source
}:

pkgs.stdenv.mkDerivation {
  pname = "beads";
  inherit version;

  src = pkgs.fetchurl {
    url = "https://github.com/steveyegge/beads/releases/download/v${version}/beads_${version}_linux_amd64.tar.gz";
    hash = "sha256-gUAJilHTuB1VSNHF5tsaLZkw5dFB7+Kkv/fQecTTIeg=";
  };

  sourceRoot = ".";
  dontConfigure = true;
  dontBuild = true;
  nativeBuildInputs = [ pkgs.autoPatchelfHook ];
  buildInputs = [ pkgs.stdenv.cc.cc.lib ];

  installPhase = ''
    runHook preInstall
    mkdir -p "$out/bin"
    install -m755 bd "$out/bin/bd"
    runHook postInstall
  '';

  meta = {
    description = "Issue tracker designed for AI-supervised coding workflows";
    homepage = "https://github.com/steveyegge/beads";
    license = pkgs.lib.licenses.mit;
    mainProgram = "bd";
    platforms = [ "x86_64-linux" ];
  };

  passthru = {
    inherit revision source;
    sourceRepository = "steveyegge/beads";
  };
}
