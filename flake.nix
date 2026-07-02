{
  description = "MeglingBot - a Pycord Discord bot";

  inputs = {
    nixpkgs.url = "nixpkgs";
  };

  outputs = {
    self,
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
  in {
    # py-cord is not packaged in nixpkgs, so we build it from PyPI.
    packages = forEachSystem (pkgs: let
      py = pythonFor pkgs;
    in {
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
    });

    devShells = forEachSystem (pkgs: let
      py = pythonFor pkgs;
    in {
      default = pkgs.mkShell {
        venvDir = ".venv";
        packages = [
          pkgs.sqlite
          pkgs.ruff # linter + formatter
          (py.withPackages (p:
            with p; [
              self.packages.${pkgs.stdenv.hostPlatform.system}.pycord
              aiosqlite
              python-dotenv
            ]))
        ];
      };
    });
  };
}
