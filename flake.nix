{
  description = "MCAP query backend — production-like dev environment (Python, GeoDjango, Celery, Postgres+PostGIS, Redis)";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
    nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };

    pyproject-build-systems = {
      url = "github:pyproject-nix/build-system-pkgs";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.uv2nix.follows = "uv2nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs = { self, nixpkgs, nixpkgs-unstable, pyproject-nix, uv2nix, pyproject-build-systems }: let
    supported = [ "aarch64-darwin" "x86_64-darwin" "x86_64-linux" ];
    forAllSystems = nixpkgs.lib.genAttrs supported;
    lib = nixpkgs.lib;
  in {

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pkgsUnstable = nixpkgs-unstable.legacyPackages.${system};
      python = pkgsUnstable.python313;
      pythonBase = pkgsUnstable.callPackage pyproject-nix.build.packages {
        inherit python;
      };
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      overlay = workspace.mkPyprojectOverlay {
        sourcePreference = "wheel";
      };
      pythonSet = pythonBase.overrideScope (lib.composeManyExtensions [
        pyproject-build-systems.overlays.wheel
        overlay
      ]);
      virtualenv = pythonSet.mkVirtualEnv "mcap-query-backend-env" workspace.deps.default;
      stdenv = pkgs.stdenv;
      gdal = pkgs.gdal;
      geos = pkgs.geos;
      postgresql = pkgs.postgresql_16.withPackages (ps: [ ps.postgis ]);
      gfortranLib = pkgsUnstable.gfortran.cc.lib;
      # GeoDjango expects a single library file path
      gdalLib = if stdenv.isDarwin
        then "${gdal}/lib/libgdal.dylib"
        else "${gdal}/lib/libgdal.so";
      geosLib = if stdenv.isDarwin
        then "${geos}/lib/libgeos_c.dylib"
        else "${geos}/lib/libgeos_c.so";
      darwinLibPath = if stdenv.isDarwin
        then "${gdal}/lib:${geos}/lib:${gfortranLib}/lib:${pkgs.openldap}/lib"
        else "";
    in {
      default = pkgs.mkShell {
        name = "mcap-query-backend";

        shell = "${pkgs.bash}/bin/bash";

        buildInputs = with pkgs; [
          virtualenv
          pkgsUnstable.uv
          gdal
          geos
          postgresql
          redis
          nodejs_22
          pnpm
        ];

        # GeoDjango / Django GIS
        GDAL_LIBRARY_PATH = gdalLib;
        GEOS_LIBRARY_PATH = geosLib;

        # Match backend/backend/settings.py and compose.yml
        POSTGRES_DB = "mcap_query_db";
        POSTGRES_USER = "postgres";
        POSTGRES_PASSWORD = "postgres";
        POSTGRES_HOST = "localhost";
        POSTGRES_PORT = "5433";
        CELERY_BROKER_URL = "redis://localhost:6379/0";
        CELERY_RESULT_BACKEND = "redis://localhost:6379/0";
        UV_NO_SYNC = "1";
        UV_PYTHON = pythonSet.python.interpreter;
        UV_PYTHON_DOWNLOADS = "never";

        # On Darwin, help dynamic linker find GDAL/GEOS deps (e.g. libgif, proj, libgfortran from OpenBLAS)
        shellHook = ''
          # Avoid Powerlevel10k zsh prompt leaking into bash (causes "bad substitution")
          export PS1="(mcap-query-backend) \\W \$ "
          # Avoid PYTHONPATH leaks from Python builders
          unset PYTHONPATH
          export GDAL_LIBRARY_PATH="${gdalLib}"
          export GEOS_LIBRARY_PATH="${geosLib}"
          export POSTGRES_DB="mcap_query_db"
          export POSTGRES_USER="postgres"
          export POSTGRES_PASSWORD="postgres"
          export POSTGRES_HOST="localhost"
          export POSTGRES_PORT="5433"
          export CELERY_BROKER_URL="redis://localhost:6379/0"
          export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
          export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
          ${lib.optionalString stdenv.isDarwin ''
            export DYLD_LIBRARY_PATH="${darwinLibPath}''${DYLD_LIBRARY_PATH:+:}$DYLD_LIBRARY_PATH"
          ''}
          echo "mcap-query-backend dev shell (production-like)"
          echo "  Python: $(python3 --version) | uv: $(uv --version)"
          echo "  Postgres 16+PostGIS and Redis from Nix (same as prod)"
          echo "  Start DB+Redis: ./scripts/start-nix-services.sh start"
          echo "  Backend:  python backend/manage.py runserver"
          echo "  Celery:   celery -A backend worker --loglevel=info"
          echo "  Frontend: cd frontend && pnpm install && pnpm run dev"
        '';
      };
    });
  };
}
