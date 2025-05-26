{
  description = "Basic python devshell";

  inputs = {
    # should be declared in USER registry with the nixos option:
    # nix.registry.nixpkgs.flake = inputs.nixpkgs;
    nixpkgs.url = "nixpkgs";
    # this is not mandatory but it will ensure this version of nixpkgs is always present on your computer
    # by using the same as your system
  };

  outputs = {
    self,
    nixpkgs,
    ...
  }: let
    lib = nixpkgs.lib;

    systems = ["x86_64-linux"];

    pkgsFor = lib.genAttrs systems (
      system:
        import nixpkgs {
          inherit system;
          config.allowUnfree = true;
        }
    );

    forEachSystem = f: lib.genAttrs systems (system: f pkgsFor.${system});
  in {
    packages = forEachSystem (pkgs:
      {

        pycord =
        let
          pname = "py_cord";
          version = "2.6.1";
        in pkgs.python3Packages.buildPythonPackage {
          inherit pname version;
          src = pkgs.fetchPypi {
            inherit pname version;
            sha256 = "sha256-NgZPIl8se73f5ULV7VgfKldE9hjgOQk8980mWaWLx5s=";
          };
          propagatedBuildInputs = with pkgs.python3Packages; [
            aiohttp
            yarl
          ];
        };

      });
    devShells = forEachSystem (pkgs: {
      default = pkgs.mkShell {
        # if package not in nixpkgs: https://github.com/nix-community/pip2nix
        # ex: nix run github:nix-community/pip2nix -- generate
        # or directly builPythonPackage
        venvDir = ".venv";
        packages = [
          pkgs.sqlite
          (pkgs.python3.withPackages (p:
            with p; [
              self.outputs.packages.${pkgs.system}.pycord
              aiosqlite
              python-dotenv
            ]))
        ];
      };
    });
  };
}
