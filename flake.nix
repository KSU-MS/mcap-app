{
  description = "MCAP query backend — production-like dev environment (Python, GeoDjango, Celery, Postgres+PostGIS, Redis)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";
  inputs.nixpkgs-unstable.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs, nixpkgs-unstable }: let
    supported = [ "aarch64-darwin" "x86_64-darwin" "x86_64-linux" ];
    forAllSystems = nixpkgs.lib.genAttrs supported;
    lib = nixpkgs.lib;
  in {

    devShells = forAllSystems (system: let
      pkgs = nixpkgs.legacyPackages.${system};
      pkgsUnstable = nixpkgs-unstable.legacyPackages.${system};
      stdenv = pkgs.stdenv;
      gdal = pkgs.gdal;
      geos = pkgs.geos;
      # Postgres 16 with PostGIS (matches compose.yml postgis/postgis:16-3.4)
      postgresql = pkgs.postgresql_16.withPackages (p: [ p.postgis ]);
      # GeoDjango expects a single library file path
      gdalLib = if stdenv.isDarwin
        then "${gdal}/lib/libgdal.dylib"
        else "${gdal}/lib/libgdal.so";
      geosLib = if stdenv.isDarwin
        then "${geos}/lib/libgeos_c.dylib"
        else "${geos}/lib/libgeos_c.so";
    in {
      default = pkgs.mkShell {
        name = "mcap-query-backend";

        shell = "${pkgs.zsh}/bin/zsh";

        buildInputs = with pkgs; [
          python313
          pkgsUnstable.uv
          gdal
          geos
          postgresql
          redis
          nodejs_22
          pnpm
          zsh
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

        # On Darwin, help dynamic linker find GDAL/GEOS deps (e.g. libgif, proj)
        shellHook = ''
          export GDAL_LIBRARY_PATH="${gdalLib}"
          export GEOS_LIBRARY_PATH="${geosLib}"
          export POSTGRES_DB="mcap_query_db"
          export POSTGRES_USER="postgres"
          export POSTGRES_PASSWORD="postgres"
          export POSTGRES_HOST="localhost"
          export POSTGRES_PORT="5433"
          export CELERY_BROKER_URL="redis://localhost:6379/0"
          export CELERY_RESULT_BACKEND="redis://localhost:6379/0"
          ${lib.optionalString stdenv.isDarwin ''
            export DYLD_LIBRARY_PATH="${gdal}/lib:${geos}/lib''${DYLD_LIBRARY_PATH:+:}$DYLD_LIBRARY_PATH"
          ''}
          echo "mcap-query-backend dev shell (production-like)"
          echo "  Python: $(python3 --version) | uv: $(uv --version)"
          echo "  Postgres 16+PostGIS and Redis from Nix (same as prod)"
          echo "  Start DB+Redis: ./scripts/start-nix-services.sh start"
          echo "  Backend:  cd backend && uv sync && uv run python manage.py runserver"
          echo "  Celery:   cd backend && uv run celery -A backend worker --loglevel=info"
          echo "  Frontend: cd frontend && pnpm install && pnpm run dev"
        '';
      };
    });
  };
}
