{
  description = "Standalone Gas City contributor runtime";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    nixpkgs-gas-city.url =
      "github:NixOS/nixpkgs/f13ff45afd1bb73e640eaa08a7066dbed07e3238";

    gascity = {
      url = "github:gastownhall/gascity/f6741d94861aa14f0253deffbe9efb1cb3a35d92";
      flake = false;
    };
    gascity-packs = {
      url = "github:gastownhall/gascity-packs/5d2a9d023edbb9ba24fdcff554e89fc3d7da72fe";
      flake = false;
    };
    beads = {
      url = "github:steveyegge/beads/bf97b73749ac3ef2fca2365b54537ac041ad4293";
      flake = false;
    };
    dolt = {
      url = "github:dolthub/dolt/v2.1.7";
      flake = false;
    };
    llm-agents = {
      url = "github:numtide/llm-agents.nix/387989ee56d550d86d46d9458ad68a55b9e0ca3b";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      nixpkgs-gas-city,
      gascity,
      gascity-packs,
      beads,
      dolt,
      llm-agents,
      ...
    }@inputs:
    let
      systems = [ "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;

      nixpkgsFor = forAllSystems (system: import nixpkgs { inherit system; });
      packageNixpkgsFor = forAllSystems (
        system: import nixpkgs-gas-city { inherit system; }
      );

      lock = builtins.fromJSON (builtins.readFile ./flake.lock);
      locked = name: (builtins.getAttr name lock.nodes).locked;

      goFor = system:
        (packageNixpkgsFor.${system}.go_1_26).overrideAttrs (_: {
          version = "1.26.6";
          src = packageNixpkgsFor.${system}.fetchurl {
            url = "https://go.dev/dl/go1.26.6.src.tar.gz";
            hash = "sha256-oHIcVMaIkBRI13rZs+x+p8R0cwdV/4kTgukuy5P/LLE=";
          };
        });

      nginxFor = system:
        (packageNixpkgsFor.${system}.nginx).overrideAttrs (_: {
          version = "1.30.2";
          src = packageNixpkgsFor.${system}.fetchurl {
            url = "https://nginx.org/download/nginx-1.30.2.tar.gz";
            hash = "sha256-ffMJCQf8o8wORW1twAzrIw2nTqiAJs7/Cv/CnbvZrEw=";
          };
        });

      buildGoModuleFor = system:
        packageNixpkgsFor.${system}.callPackage
          (packageNixpkgsFor.${system}.path + "/pkgs/build-support/go/module.nix")
          {
            go = goFor system;
          };

      gascityFor = system:
        import ./nix/packages/gascity.nix {
          pkgs = packageNixpkgsFor.${system};
          source = gascity;
          buildGoModule = buildGoModuleFor system;
          revision = (locked "gascity").rev;
        };

      beadsFor = system:
        import ./nix/packages/beads.nix {
          pkgs = packageNixpkgsFor.${system};
          source = beads;
          buildGoModule = buildGoModuleFor system;
          revision = (locked "beads").rev;
        };

      doltFor = system:
        import ./nix/packages/dolt.nix {
          pkgs = packageNixpkgsFor.${system};
          source = dolt;
          buildGoModule = buildGoModuleFor system;
        };

      copilotFor = system: llm-agents.packages.${system}.copilot-cli;
      tinyauthFor = system: packageNixpkgsFor.${system}.tinyauth;
      nginxPackageFor = nginxFor;
      goPackageFor = goFor;

      sourceManifestFor = system:
        (import ./nix/source-manifest.nix {
          pkgs = nixpkgsFor.${system};
          lockFile = ./flake.lock;
          script = ./scripts/source-manifest.py;
          packageInfo = {
            gascity = {
              version = (gascityFor system).version;
            };
            beads = {
              version = (beadsFor system).version;
            };
            dolt = {
              version = (doltFor system).version;
            };
            copilotCli = {
              version = (copilotFor system).version;
            };
            go = {
              version = (goPackageFor system).version;
            };
            tinyauth = {
              version = (tinyauthFor system).version;
            };
            nginx = {
              version = (nginxPackageFor system).version;
            };
          };
        });

      contributorFor = system:
        import ./nix/packages/contributor.nix {
          pkgs = nixpkgsFor.${system};
          gascity = gascityFor system;
          beads = beadsFor system;
          dolt = doltFor system;
          copilot = copilotFor system;
          go = goPackageFor system;
          tinyauth = tinyauthFor system;
          nginx = nginxPackageFor system;
          sourceManifest = (sourceManifestFor system).manifest;
        };
    in
    {
      packages = forAllSystems (system: {
        gascity = gascityFor system;
        beads = beadsFor system;
        dolt = doltFor system;
        "gas-city-contributor" = contributorFor system;
      });

      devShells = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
          contributor = contributorFor system;
        in
        {
          default = pkgs.mkShellNoCC {
            name = "gas-city-dev";
            packages = [
              contributor
              pkgs.nix
              pkgs.python3
              pkgs.python3Packages.pytest
              pkgs.jq
              pkgs.ripgrep
              pkgs.git
              pkgs.gh
              pkgs.curl
              pkgs.shellcheck
            ];
            shellHook = ''
              export GC_CONTRIBUTOR_ROOT="${contributor}"
              export PATH="${contributor}/bin:$PATH"
            '';
          };
        });

      checks = forAllSystems (system:
        let
          pkgs = nixpkgsFor.${system};
          contributor = contributorFor system;
          sourceManifest = sourceManifestFor system;
        in
        {
          package-smoke = import ./tests/smoke/package.nix {
            inherit pkgs;
            gasCityContributor = contributor;
            gascityRevision = (locked "gascity").rev;
            gascityPacksRevision = (locked "gascity-packs").rev;
            beadsRevision = (locked "beads").rev;
            llmAgentsRevision = (locked "llm-agents").rev;
            doltVersion = (doltFor system).version;
            goVersion = (goPackageFor system).version;
            copilotVersion = (copilotFor system).version;
            tinyauthVersion = (tinyauthFor system).version;
            nginxVersion = (nginxPackageFor system).version;
          };
          source-manifest = sourceManifest.check;
        });
    };
}
