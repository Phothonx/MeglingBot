{
  description = "MeglingBot - a Pycord Discord bot";

  inputs = {
    nixpkgs.url = "nixpkgs";
  };

  outputs = {
    nixpkgs,
    ...
  }: let
    lib = nixpkgs.lib;
    systems = ["x86_64-linux"];

    pkgsFor = lib.genAttrs systems (system:
      import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      });

    forEachSystem = f: lib.genAttrs systems (system: f pkgsFor.${system});

    # Pinned to 3.12: py-cord 2.6.1 imports the `audioop` module, removed from
    # the stdlib in Python 3.13.
    pythonFor = pkgs: pkgs.python312;

    # Everything is derived per-system from this single evaluation, so the
    # runtime dependency list is written once and reused by both the package
    # and the devshell.
    perSystem = forEachSystem (pkgs: let
      py = pythonFor pkgs;

      # py-cord is not packaged in nixpkgs, so we build it from PyPI.
      pycord = py.pkgs.buildPythonPackage rec {
        pname = "py_cord";
        version = "2.8.0";
        pyproject = true;
        src = pkgs.fetchPypi {
          inherit pname version;
          sha256 = "sha256-V6fv76gOf274kPv8BU1oZ4LDR8nk2G+nyR965ShbNT8=";
        };
        build-system = with py.pkgs; [setuptools setuptools-scm];
        # py-cord 2.8.0 caps setuptools at <=80.9.0, but nixpkgs ships 80.10.1;
        # drop the upper bound so the build backend accepts it.
        postPatch = ''
          substituteInPlace pyproject.toml \
            --replace-fail "setuptools>=77.0.3,<=80.9.0" "setuptools>=77.0.3"
        '';
        propagatedBuildInputs = with py.pkgs; [aiohttp yarl];
      };

      # The bot's runtime Python dependencies — the single source of truth.
      pythonDeps = p: [
        pycord
        p.aiosqlite
        p.python-dotenv
        p.emoji # :shortcode: -> unicode conversion
      ];
      pythonEnv = py.withPackages pythonDeps;
    in {
      inherit pycord;

      # Runnable bot: target for `nix run` or a systemd ExecStart.
      # main.py resolves db/ and logs/ relative to the working directory, so the
      # deployment picks a writable state dir; the code itself stays read-only.
      meglingbot = pkgs.stdenv.mkDerivation {
        pname = "meglingbot";
        version = "0.1.0";
        src = ./.;
        nativeBuildInputs = [pkgs.makeWrapper];
        dontBuild = true;
        installPhase = ''
          runHook preInstall
          mkdir -p $out/share/meglingbot
          cp -r main.py megling $out/share/meglingbot/
          makeWrapper ${pythonEnv}/bin/python $out/bin/meglingbot \
            --add-flags "$out/share/meglingbot/main.py"
          runHook postInstall
        '';
      };

      # Same interpreter as the package, plus the dev-only tooling.
      devShell = pkgs.mkShell {
        venvDir = ".venv";
        packages = [
          pkgs.sqlite
          pkgs.ruff # linter + formatter
          pythonEnv
        ];
      };
    });

    forSystem = pkgs: perSystem.${pkgs.stdenv.hostPlatform.system};
  in {
    packages = forEachSystem (pkgs: let
      p = forSystem pkgs;
    in {
      inherit (p) pycord meglingbot;
      default = p.meglingbot;
    });

    devShells = forEachSystem (pkgs: {
      default = (forSystem pkgs).devShell;
    });
  };
}