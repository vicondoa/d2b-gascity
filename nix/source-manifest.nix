{ pkgs
, lockFile
, script
, packageInfo
}:

let
  packageInfoFile = pkgs.writeText "gas-city-package-info.json" (
    builtins.toJSON packageInfo
  );

  runManifest = output:
    ''
      ${pkgs.python3}/bin/python3 ${script} \
        --lock ${lockFile} \
        --packages ${packageInfoFile} \
        --output ${output}
    '';
in
{
  manifest = pkgs.runCommand "gas-city-source-manifest" {
    nativeBuildInputs = [ pkgs.python3 ];
  } ''
    set -euo pipefail
    mkdir -p "$out/share/gas-city-contributor"
    ${runManifest "$out/share/gas-city-contributor/sources.json"}
  '';

  check = pkgs.runCommand "gas-city-source-manifest-check" {
    nativeBuildInputs = [
      pkgs.coreutils
      pkgs.python3
    ];
  } ''
    set -euo pipefail
    first="$TMPDIR/first.json"
    second="$TMPDIR/second.json"
    ${runManifest "$first"}
    ${runManifest "$second"}
    cmp "$first" "$second"
    ${pkgs.python3}/bin/python3 - "$first" <<'PY'
    import pathlib
    import sys

    data = pathlib.Path(sys.argv[1]).read_bytes()
    if not data.isascii():
        raise SystemExit("source manifest is not ASCII")
    PY
    mkdir -p "$out"
    printf '%s\n' "source-manifest: deterministic and ASCII-only" > "$out/result"
  '';
}
