{
  description = "Include your terminal Claude Code sessions in the desktop app's list, and move them between accounts";

  inputs.nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      # The store this reads lives under ~/.config/Claude, which is where the
      # app keeps it on Linux only; macOS puts it under ~/Library/Application
      # Support and has not been looked at.
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f nixpkgs.legacyPackages.${system});
    in
    {
      packages = forAllSystems (pkgs: rec {
        inclaude = pkgs.python3Packages.buildPythonApplication {
          pname = "inclaude";
          version = "0.1.0";
          pyproject = true;
          src = ./.;
          build-system = [ pkgs.python3Packages.hatchling ];
          meta = {
            description = "Include your terminal Claude Code sessions in the desktop app's list, and move them between accounts";
            homepage = "https://github.com/clement-songis/inclaude";
            license = pkgs.lib.licenses.mit;
            mainProgram = "inclaude";
            platforms = systems;
          };
        };
        default = inclaude;
      });

      apps = forAllSystems (pkgs: {
        default = {
          type = "app";
          program = "${self.packages.${pkgs.stdenv.hostPlatform.system}.default}/bin/inclaude";
        };
      });

      overlays.default = final: _prev: {
        inclaude = self.packages.${final.stdenv.hostPlatform.system}.inclaude;
      };

      devShells = forAllSystems (pkgs: {
        default = pkgs.mkShell {
          packages = [
            pkgs.python3
            pkgs.python3Packages.hatchling
          ];
        };
      });
    };
}
