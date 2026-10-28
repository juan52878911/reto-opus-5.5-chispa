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
        # Servidor sin ORT ni cgo (L2 queda en stub). Con la imagen OCI (server/deploy/Dockerfile) sí hay L2.
        # No probado: nix no está en la VM de desarrollo. vendorHash es un marcador: la primera construcción
        # falla con el hash real (`nix build .#chispa-server`) y se pega aquí. Si kindling no es accesible desde
        # el sandbox de nix, hay que vendorizarlo (go mod vendor en server/) y poner vendorHash = null.
        packages.chispa-server = pkgs.buildGoModule {
          pname = "chispa-server";
          version = "0.1.0";
          src = ./..;
          modRoot = "server";
          subPackages = [ "cmd/chispa-server" "cmd/carga" ];
          vendorHash = pkgs.lib.fakeHash;
          env.CGO_ENABLED = "0";
          ldflags = [ "-s" "-w" ];
          doCheck = false;
        };
        packages.default = self.packages.${system}.chispa-server;

        devShells.default = pkgs.mkShell {
          packages = [ python pkgs.go_1_27 pkgs.gnumake ];
        };
      });
}
