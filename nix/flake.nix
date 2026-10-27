{
  description = "Chispa: entorno de desarrollo (Python de ML + Go 1.27)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312.withPackages (ps: with ps; [
          torch
          sentence-transformers
          onnxruntime
          optimum
        ]);
      in {
        devShells.default = pkgs.mkShell {
          packages = [ python pkgs.go_1_27 pkgs.gnumake ];
        };
      });
}
