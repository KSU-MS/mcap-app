{
  description = "MCAP query backend flake (dev + Ubuntu + NixOS deploy)";

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

  outputs =
    { self
    , nixpkgs
    , nixpkgs-unstable
    , pyproject-nix
    , uv2nix
    , pyproject-build-systems
    ,
    }:
    let
      lib = nixpkgs.lib;
      supportedSystems = [
        "aarch64-darwin"
        "x86_64-darwin"
        "aarch64-linux"
        "x86_64-linux"
      ];
      forAllSystems = lib.genAttrs supportedSystems;

      mkSystem = system:
        let
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

          gdalLib =
            if stdenv.isDarwin
            then "${gdal}/lib/libgdal.dylib"
            else "${gdal}/lib/libgdal.so";

          geosLib =
            if stdenv.isDarwin
            then "${geos}/lib/libgeos_c.dylib"
            else "${geos}/lib/libgeos_c.so";

          darwinLibPath =
            if stdenv.isDarwin
            then "${gdal}/lib:${geos}/lib:${gfortranLib}/lib:${pkgs.openldap}/lib"
            else "";

          backendCode = "${self}/backend";
          frontendCode = "${self}/frontend";
          pythonSitePackages = "${virtualenv}/${python.sitePackages}";

          frontendVersion = "0.1.0";
          frontendDeps = pkgs.pnpm.fetchDeps {
            pname = "mcap-frontend-deps";
            version = frontendVersion;
            src = frontendCode;
            hash = "sha256-oMw8UBlkQWdQFjkLCMi/AA2uddm70fbUA4IKqR1CEoA=";
          };

          frontendPackage = pkgs.stdenv.mkDerivation {
            pname = "mcap-frontend";
            version = frontendVersion;
            src = frontendCode;
            nativeBuildInputs = [
              pkgs.nodejs_22
              pkgs.pnpm.configHook
            ];
            pnpmDeps = frontendDeps;

            buildPhase = ''
              runHook preBuild
              export HOME="$TMPDIR"
              export NEXT_TELEMETRY_DISABLED=1
              pnpm run build
              runHook postBuild
            '';

            installPhase = ''
              runHook preInstall
              mkdir -p "$out/frontend"
              cp -r .next "$out/frontend/.next"
              cp -r public "$out/frontend/public"
              cp -r node_modules "$out/frontend/node_modules"
              cp package.json "$out/frontend/package.json"
              cp next.config.ts "$out/frontend/next.config.ts"
              runHook postInstall
            '';
          };

          frontendRunner = pkgs.writeShellApplication {
            name = "mcap-frontend";
            runtimeInputs = [ pkgs.nodejs_22 ];
            text = ''
              set -euo pipefail

              export NEXT_TELEMETRY_DISABLED=1
              export NODE_ENV="production"
              export FRONTEND_HOST="''${FRONTEND_HOST:-127.0.0.1}"
              export FRONTEND_PORT="''${FRONTEND_PORT:-13000}"

              exec "${pkgs.nodejs_22}/bin/node" \
                "${frontendPackage}/frontend/node_modules/next/dist/bin/next" start \
                -H "$FRONTEND_HOST" \
                -p "$FRONTEND_PORT" \
                "${frontendPackage}/frontend"
            '';
          };

          backendRunner = pkgs.writeShellApplication {
            name = "mcap-backend";
            runtimeInputs = [
              virtualenv
              pkgsUnstable.python313Packages.gunicorn
            ];
            text = ''
                  set -euo pipefail

                  export PYTHONDONTWRITEBYTECODE=1
                  export DJANGO_SETTINGS_MODULE="''${DJANGO_SETTINGS_MODULE:-backend.settings}"
                  export DJANGO_HOST="''${DJANGO_HOST:-127.0.0.1}"
                  export DJANGO_PORT="''${DJANGO_PORT:-18000}"
                  export GUNICORN_WORKERS="''${GUNICORN_WORKERS:-3}"
                  export GUNICORN_TIMEOUT="''${GUNICORN_TIMEOUT:-90}"
                  export MEDIA_ROOT="''${MEDIA_ROOT:-/var/lib/mcap-query-backend/media}"

                  export GDAL_LIBRARY_PATH="${gdalLib}"
                  export GEOS_LIBRARY_PATH="${geosLib}"
              export PYTHONPATH="${pythonSitePackages}:${backendCode}''${PYTHONPATH:+:$PYTHONPATH}"
              ${lib.optionalString stdenv.isDarwin ''
                export DYLD_LIBRARY_PATH="${darwinLibPath}''${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
              ''}

                  exec gunicorn backend.wsgi:application \
                    --chdir "${backendCode}" \
                    --bind "$DJANGO_HOST:$DJANGO_PORT" \
                    --workers "$GUNICORN_WORKERS" \
                    --timeout "$GUNICORN_TIMEOUT" \
                    --access-logfile - \
                    --error-logfile -
            '';
          };

          celeryRunner = pkgs.writeShellApplication {
            name = "mcap-celery";
            runtimeInputs = [ virtualenv ];
            text = ''
                  set -euo pipefail

                  export PYTHONDONTWRITEBYTECODE=1
                  export DJANGO_SETTINGS_MODULE="''${DJANGO_SETTINGS_MODULE:-backend.settings}"
                  export CELERY_LOG_LEVEL="''${CELERY_LOG_LEVEL:-info}"
                  export CELERY_CONCURRENCY="''${CELERY_CONCURRENCY:-4}"
                  export CELERY_POOL="''${CELERY_POOL:-prefork}"

                  export GDAL_LIBRARY_PATH="${gdalLib}"
                  export GEOS_LIBRARY_PATH="${geosLib}"
              export PYTHONPATH="${pythonSitePackages}:${backendCode}''${PYTHONPATH:+:$PYTHONPATH}"
              ${lib.optionalString stdenv.isDarwin ''
                export DYLD_LIBRARY_PATH="${darwinLibPath}''${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
              ''}

              exec "${virtualenv}/bin/celery" \
                --workdir "${backendCode}" \
                -A backend worker \
                --loglevel "$CELERY_LOG_LEVEL" \
                --pool "$CELERY_POOL" \
                --concurrency "$CELERY_CONCURRENCY"
            '';
          };

          migrateRunner = pkgs.writeShellApplication {
            name = "mcap-migrate";
            runtimeInputs = [ virtualenv ];
            text = ''
                  set -euo pipefail

                  export PYTHONDONTWRITEBYTECODE=1
                  export DJANGO_SETTINGS_MODULE="''${DJANGO_SETTINGS_MODULE:-backend.settings}"
                  export GDAL_LIBRARY_PATH="${gdalLib}"
                  export GEOS_LIBRARY_PATH="${geosLib}"
              export PYTHONPATH="${pythonSitePackages}:${backendCode}''${PYTHONPATH:+:$PYTHONPATH}"
              ${lib.optionalString stdenv.isDarwin ''
                export DYLD_LIBRARY_PATH="${darwinLibPath}''${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
              ''}

                  exec "${virtualenv}/bin/python" "${backendCode}/manage.py" migrate --noinput
            '';
          };
        in
        {
          packages = {
            default = backendRunner;
            backend = backendRunner;
            celery = celeryRunner;
            migrate = migrateRunner;
            frontend = frontendPackage;
            frontend-runner = frontendRunner;
            ubuntu-systemd-unit = pkgs.writeText "mcap-query-backend.service" ''
              [Unit]
              Description=MCAP Query Backend (gunicorn)
              Wants=network-online.target
              After=network-online.target

              [Service]
              Type=simple
              User=mcap
              Group=mcap
              EnvironmentFile=/etc/mcap-query-backend.env
              ExecStart=${backendRunner}/bin/mcap-backend
              Restart=always
              RestartSec=3
              NoNewPrivileges=true
              PrivateTmp=true

              [Install]
              WantedBy=multi-user.target
            '';
            ubuntu-frontend-systemd-unit = pkgs.writeText "mcap-query-frontend.service" ''
              [Unit]
              Description=MCAP Frontend (Next.js)
              Wants=network-online.target
              After=network-online.target

              [Service]
              Type=simple
              User=mcap
              Group=mcap
              EnvironmentFile=/etc/mcap-query-backend.env
              ExecStart=${frontendRunner}/bin/mcap-frontend
              Restart=always
              RestartSec=3
              NoNewPrivileges=true
              PrivateTmp=true

              [Install]
              WantedBy=multi-user.target
            '';
          };

          apps = {
            default = {
              type = "app";
              program = "${backendRunner}/bin/mcap-backend";
            };
            backend = {
              type = "app";
              program = "${backendRunner}/bin/mcap-backend";
            };
            celery = {
              type = "app";
              program = "${celeryRunner}/bin/mcap-celery";
            };
            migrate = {
              type = "app";
              program = "${migrateRunner}/bin/mcap-migrate";
            };
            frontend = {
              type = "app";
              program = "${frontendRunner}/bin/mcap-frontend";
            };
          };

          checks = {
            backend-bytecode = pkgs.runCommand "backend-bytecode"
              {
                src = ./.;
                nativeBuildInputs = [ virtualenv ];
              } ''
              cp -r "$src" ./src
              chmod -R u+w ./src
              cd ./src
              ${virtualenv}/bin/python -m compileall -q backend
              touch $out
            '';
            frontend-build = frontendPackage;
          };

          devShells.default = pkgs.mkShell {
            name = "mcap-query-backend";
            shell = "${pkgs.bash}/bin/bash";

            buildInputs = [
              virtualenv
              pkgsUnstable.uv
              gdal
              geos
              postgresql
              pkgs.redis
              pkgs.nodejs_22
              pkgs.pnpm
            ];

            GDAL_LIBRARY_PATH = gdalLib;
            GEOS_LIBRARY_PATH = geosLib;
            POSTGRES_DB = "mcap_query_db";
            POSTGRES_USER = "postgres";
            POSTGRES_PASSWORD = "postgres";
            POSTGRES_HOST = "localhost";
            UV_NO_SYNC = "1";
            UV_PYTHON = pythonSet.python.interpreter;
            UV_PYTHON_DOWNLOADS = "never";

            shellHook = ''
                  export PS1="(mcap-query-backend) \\W \$ "
                  unset PYTHONPATH
                  export REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)

                  if [[ -f "$REPO_ROOT/.env" ]]; then
                    set -a
                    source "$REPO_ROOT/.env"
                    set +a
                  fi

                  export GDAL_LIBRARY_PATH="${gdalLib}"
                  export GEOS_LIBRARY_PATH="${geosLib}"
                  export POSTGRES_DB="''${POSTGRES_DB:-mcap_query_db}"
                  export POSTGRES_USER="''${POSTGRES_USER:-postgres}"
                  export POSTGRES_PASSWORD="''${POSTGRES_PASSWORD:-postgres}"
                  export POSTGRES_HOST="''${POSTGRES_HOST:-localhost}"
                  export POSTGRES_PORT="''${POSTGRES_PORT:-5433}"
                  export REDIS_HOST="''${REDIS_HOST:-localhost}"
                  export REDIS_PORT="''${REDIS_PORT:-6379}"
                  export DJANGO_HOST="''${DJANGO_HOST:-127.0.0.1}"
                  export DJANGO_PORT="''${DJANGO_PORT:-8000}"
                  export FRONTEND_PORT="''${FRONTEND_PORT:-3000}"
                  export CELERY_BROKER_URL="''${CELERY_BROKER_URL:-redis://$REDIS_HOST:$REDIS_PORT/0}"
                  export CELERY_RESULT_BACKEND="''${CELERY_RESULT_BACKEND:-redis://$REDIS_HOST:$REDIS_PORT/0}"
                  ${lib.optionalString stdenv.isDarwin ''
                export DYLD_LIBRARY_PATH="${darwinLibPath}''${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
              ''}
                  echo "mcap-query-backend dev shell"
                  echo "  Backend app: nix run .#backend"
                  echo "  Celery app:  nix run .#celery"
                  echo "  Migrations:  nix run .#migrate"
                  echo "  Frontend:    nix run .#frontend"
            '';
          };

          formatter = pkgs.nixpkgs-fmt;
        };
    in
    {
      packages = forAllSystems (system: (mkSystem system).packages);
      apps = forAllSystems (system: (mkSystem system).apps);
      checks = forAllSystems (system: (mkSystem system).checks);
      devShells = forAllSystems (system: (mkSystem system).devShells);
      formatter = forAllSystems (system: (mkSystem system).formatter);

      nixosModules.default =
        { config
        , lib
        , pkgs
        , ...
        }:
        let
          cfg = config.services.mcap-query-backend;
        in
        {
          options.services.mcap-query-backend = with lib; {
            enable = mkEnableOption "MCAP query backend";

            package = mkOption {
              type = types.package;
              default = self.packages.${pkgs.system}.backend;
              description = "Backend executable package.";
            };

            celeryPackage = mkOption {
              type = types.package;
              default = self.packages.${pkgs.system}.celery;
              description = "Celery executable package.";
            };

            migratePackage = mkOption {
              type = types.package;
              default = self.packages.${pkgs.system}.migrate;
              description = "Migration executable package.";
            };

            host = mkOption {
              type = types.str;
              default = "127.0.0.1";
              description = "Django bind host.";
            };

            port = mkOption {
              type = types.port;
              default = 18000;
              description = "Django bind port.";
            };

            openFirewall = mkOption {
              type = types.bool;
              default = false;
              description = "Open backend port in firewall.";
            };

            runMigrations = mkOption {
              type = types.bool;
              default = true;
              description = "Run migrations before starting backend.";
            };

            user = mkOption {
              type = types.str;
              default = "mcap-query-backend";
              description = "System user running backend and celery.";
            };

            group = mkOption {
              type = types.str;
              default = "mcap-query-backend";
              description = "System group running backend and celery.";
            };

            createUser = mkOption {
              type = types.bool;
              default = true;
              description = "Whether to create service user/group.";
            };

            mediaRoot = mkOption {
              type = types.str;
              default = "/var/lib/mcap-query-backend/media";
              description = "Writable media directory.";
            };

            environmentFile = mkOption {
              type = types.nullOr types.path;
              default = null;
              description = "Optional environment file for secrets/overrides.";
            };

            extraEnvironment = mkOption {
              type = types.attrsOf types.str;
              default = { };
              description = "Additional environment variables.";
            };

            gunicornWorkers = mkOption {
              type = types.ints.positive;
              default = 3;
              description = "Gunicorn worker count.";
            };

            gunicornTimeout = mkOption {
              type = types.ints.positive;
              default = 90;
              description = "Gunicorn timeout in seconds.";
            };

            celeryEnable = mkOption {
              type = types.bool;
              default = true;
              description = "Enable celery worker service.";
            };

            celeryConcurrency = mkOption {
              type = types.ints.positive;
              default = 4;
              description = "Celery worker concurrency.";
            };

            redis = {
              enable = mkOption {
                type = types.bool;
                default = true;
                description = "Provision a local Redis instance.";
              };

              host = mkOption {
                type = types.str;
                default = "127.0.0.1";
                description = "Redis host used by backend/celery.";
              };

              port = mkOption {
                type = types.port;
                default = 6380;
                description = "Redis port used by backend/celery.";
              };
            };

            database = {
              enable = mkOption {
                type = types.bool;
                default = true;
                description = "Provision local PostgreSQL with PostGIS.";
              };

              name = mkOption {
                type = types.str;
                default = "mcap_query_db";
                description = "Database name.";
              };

              user = mkOption {
                type = types.str;
                default = "mcap-query-backend";
                description = "Database user.";
              };

              host = mkOption {
                type = types.str;
                default = "/run/postgresql";
                description = "Database host or socket path.";
              };

              port = mkOption {
                type = types.port;
                default = 5433;
                description = "Database port (used when host is TCP).";
              };
            };

            frontend = {
              enable = mkOption {
                type = types.bool;
                default = true;
                description = "Enable Next.js frontend service.";
              };

              package = mkOption {
                type = types.package;
                default = self.packages.${pkgs.system}.frontend-runner;
                description = "Frontend runner package.";
              };

              host = mkOption {
                type = types.str;
                default = "127.0.0.1";
                description = "Frontend bind host.";
              };

              port = mkOption {
                type = types.port;
                default = 13000;
                description = "Frontend bind port.";
              };

              openFirewall = mkOption {
                type = types.bool;
                default = false;
                description = "Open frontend port in firewall.";
              };

              environmentFile = mkOption {
                type = types.nullOr types.path;
                default = null;
                description = "Optional environment file for frontend overrides.";
              };

              extraEnvironment = mkOption {
                type = types.attrsOf types.str;
                default = { };
                description = "Additional frontend environment variables.";
              };
            };

            nginx = {
              enable = mkOption {
                type = types.bool;
                default = false;
                description = "Enable nginx reverse proxy.";
              };

              serverName = mkOption {
                type = types.str;
                default = "_";
                description = "nginx virtual host server name.";
              };

              forceSSL = mkOption {
                type = types.bool;
                default = false;
                description = "Force HTTPS redirects in nginx virtual host.";
              };

              enableACME = mkOption {
                type = types.bool;
                default = false;
                description = "Enable ACME cert management in nginx virtual host.";
              };
            };
          };

          config = lib.mkIf cfg.enable (lib.mkMerge [
            {
              assertions = [
                {
                  assertion = cfg.port != cfg.redis.port;
                  message = "services.mcap-query-backend.port must differ from redis.port";
                }
                {
                  assertion = cfg.port != cfg.database.port;
                  message = "services.mcap-query-backend.port must differ from database.port";
                }
                {
                  assertion = cfg.redis.port != cfg.database.port;
                  message = "services.mcap-query-backend.redis.port must differ from database.port";
                }
                {
                  assertion = (!cfg.frontend.enable) || (cfg.frontend.port != cfg.port);
                  message = "services.mcap-query-backend.frontend.port must differ from backend port";
                }
                {
                  assertion = (!cfg.frontend.enable) || (cfg.frontend.port != cfg.redis.port);
                  message = "services.mcap-query-backend.frontend.port must differ from redis port";
                }
                {
                  assertion = (!cfg.frontend.enable) || (cfg.frontend.port != cfg.database.port);
                  message = "services.mcap-query-backend.frontend.port must differ from database port";
                }
              ];

              users.groups = lib.mkIf cfg.createUser {
                "${cfg.group}" = { };
              };

              users.users = lib.mkIf cfg.createUser {
                "${cfg.user}" = {
                  isSystemUser = true;
                  group = cfg.group;
                  home = "/var/lib/mcap-query-backend";
                  createHome = true;
                };
              };

              systemd.tmpfiles.rules = [
                "d ${cfg.mediaRoot} 0750 ${cfg.user} ${cfg.group} -"
              ];

              systemd.services.mcap-query-backend-migrate = lib.mkIf cfg.runMigrations {
                description = "MCAP query backend migrations";
                after =
                  [ "network-online.target" ]
                  ++ lib.optional cfg.database.enable "postgresql.service"
                  ++ lib.optional cfg.redis.enable "redis-mcap-query.service";
                wants = [ "network-online.target" ];
                serviceConfig = {
                  Type = "oneshot";
                  User = cfg.user;
                  Group = cfg.group;
                  WorkingDirectory = "${self}";
                  EnvironmentFile = lib.optional (cfg.environmentFile != null) cfg.environmentFile;
                  NoNewPrivileges = true;
                  PrivateTmp = true;
                  ProtectSystem = "strict";
                  ProtectHome = true;
                  ReadWritePaths = [ cfg.mediaRoot ];
                  ExecStart = "${cfg.migratePackage}/bin/mcap-migrate";
                };
                environment = {
                  DJANGO_HOST = cfg.host;
                  DJANGO_PORT = toString cfg.port;
                  POSTGRES_DB = cfg.database.name;
                  POSTGRES_USER = cfg.database.user;
                  POSTGRES_HOST = cfg.database.host;
                  POSTGRES_PORT = toString cfg.database.port;
                  REDIS_HOST = cfg.redis.host;
                  REDIS_PORT = toString cfg.redis.port;
                  CELERY_BROKER_URL = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  CELERY_RESULT_BACKEND = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  MEDIA_ROOT = cfg.mediaRoot;
                } // cfg.extraEnvironment;
              };

              systemd.services.mcap-query-backend = {
                description = "MCAP query backend";
                wantedBy = [ "multi-user.target" ];
                after =
                  [ "network-online.target" ]
                  ++ lib.optional cfg.database.enable "postgresql.service"
                  ++ lib.optional cfg.redis.enable "redis-mcap-query.service"
                  ++ lib.optional cfg.runMigrations "mcap-query-backend-migrate.service";
                wants = [ "network-online.target" ];
                requires = lib.optional cfg.runMigrations "mcap-query-backend-migrate.service";
                serviceConfig = {
                  Type = "simple";
                  User = cfg.user;
                  Group = cfg.group;
                  WorkingDirectory = "${self}";
                  EnvironmentFile = lib.optional (cfg.environmentFile != null) cfg.environmentFile;
                  ExecStart = "${cfg.package}/bin/mcap-backend";
                  Restart = "always";
                  RestartSec = "3s";
                  NoNewPrivileges = true;
                  PrivateTmp = true;
                  PrivateDevices = true;
                  ProtectSystem = "strict";
                  ProtectHome = true;
                  ProtectKernelTunables = true;
                  ProtectKernelModules = true;
                  ProtectControlGroups = true;
                  RestrictSUIDSGID = true;
                  LockPersonality = true;
                  MemoryDenyWriteExecute = true;
                  CapabilityBoundingSet = "";
                  RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
                  ReadWritePaths = [ cfg.mediaRoot ];
                };
                environment = {
                  DJANGO_HOST = cfg.host;
                  DJANGO_PORT = toString cfg.port;
                  GUNICORN_WORKERS = toString cfg.gunicornWorkers;
                  GUNICORN_TIMEOUT = toString cfg.gunicornTimeout;
                  POSTGRES_DB = cfg.database.name;
                  POSTGRES_USER = cfg.database.user;
                  POSTGRES_HOST = cfg.database.host;
                  POSTGRES_PORT = toString cfg.database.port;
                  REDIS_HOST = cfg.redis.host;
                  REDIS_PORT = toString cfg.redis.port;
                  CELERY_BROKER_URL = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  CELERY_RESULT_BACKEND = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  MEDIA_ROOT = cfg.mediaRoot;
                } // cfg.extraEnvironment;
              };

              systemd.services.mcap-query-celery = lib.mkIf cfg.celeryEnable {
                description = "MCAP query celery worker";
                wantedBy = [ "multi-user.target" ];
                after =
                  [ "network-online.target" "mcap-query-backend.service" ]
                  ++ lib.optional cfg.redis.enable "redis-mcap-query.service";
                wants = [ "network-online.target" ];
                serviceConfig = {
                  Type = "simple";
                  User = cfg.user;
                  Group = cfg.group;
                  WorkingDirectory = "${self}";
                  EnvironmentFile = lib.optional (cfg.environmentFile != null) cfg.environmentFile;
                  ExecStart = "${cfg.celeryPackage}/bin/mcap-celery";
                  Restart = "always";
                  RestartSec = "3s";
                  NoNewPrivileges = true;
                  PrivateTmp = true;
                  PrivateDevices = true;
                  ProtectSystem = "strict";
                  ProtectHome = true;
                  ProtectKernelTunables = true;
                  ProtectKernelModules = true;
                  ProtectControlGroups = true;
                  RestrictSUIDSGID = true;
                  LockPersonality = true;
                  MemoryDenyWriteExecute = true;
                  CapabilityBoundingSet = "";
                  RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
                  ReadWritePaths = [ cfg.mediaRoot ];
                };
                environment = {
                  CELERY_CONCURRENCY = toString cfg.celeryConcurrency;
                  POSTGRES_DB = cfg.database.name;
                  POSTGRES_USER = cfg.database.user;
                  POSTGRES_HOST = cfg.database.host;
                  POSTGRES_PORT = toString cfg.database.port;
                  REDIS_HOST = cfg.redis.host;
                  REDIS_PORT = toString cfg.redis.port;
                  CELERY_BROKER_URL = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  CELERY_RESULT_BACKEND = "redis://${cfg.redis.host}:${toString cfg.redis.port}/0";
                  MEDIA_ROOT = cfg.mediaRoot;
                } // cfg.extraEnvironment;
              };

              systemd.services.mcap-query-frontend = lib.mkIf cfg.frontend.enable {
                description = "MCAP query frontend";
                wantedBy = [ "multi-user.target" ];
                after = [ "network-online.target" "mcap-query-backend.service" ];
                wants = [ "network-online.target" ];
                requires = [ "mcap-query-backend.service" ];
                serviceConfig = {
                  Type = "simple";
                  User = cfg.user;
                  Group = cfg.group;
                  WorkingDirectory = "${self}";
                  EnvironmentFile =
                    let
                      frontendEnvFile =
                        if cfg.frontend.environmentFile != null
                        then cfg.frontend.environmentFile
                        else cfg.environmentFile;
                    in
                    lib.optional (frontendEnvFile != null) frontendEnvFile;
                  ExecStart = "${cfg.frontend.package}/bin/mcap-frontend";
                  Restart = "always";
                  RestartSec = "3s";
                  NoNewPrivileges = true;
                  PrivateTmp = true;
                  PrivateDevices = true;
                  ProtectSystem = "strict";
                  ProtectHome = true;
                  ProtectKernelTunables = true;
                  ProtectKernelModules = true;
                  ProtectControlGroups = true;
                  RestrictSUIDSGID = true;
                  LockPersonality = true;
                  MemoryDenyWriteExecute = true;
                  CapabilityBoundingSet = "";
                  RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
                  ReadWritePaths = [ cfg.mediaRoot ];
                };
                environment = {
                  FRONTEND_HOST = cfg.frontend.host;
                  FRONTEND_PORT = toString cfg.frontend.port;
                  NEXT_PUBLIC_API_BASE_URL = "/api";
                }
                // cfg.extraEnvironment
                // cfg.frontend.extraEnvironment;
              };

              networking.firewall.allowedTCPPorts =
                lib.optionals cfg.openFirewall [ cfg.port ]
                ++ lib.optionals cfg.frontend.openFirewall [ cfg.frontend.port ];
            }

            (lib.mkIf cfg.database.enable {
              services.postgresql = {
                enable = true;
                package = pkgs.postgresql_16.withPackages (ps: [ ps.postgis ]);
                settings = {
                  port = cfg.database.port;
                };
                initialScript = pkgs.writeText "mcap-query-backend-postgresql-init.sql" ''
                  \connect ${cfg.database.name}
                  CREATE EXTENSION IF NOT EXISTS postgis;
                '';
                ensureDatabases = [ cfg.database.name ];
                ensureUsers = [
                  {
                    name = cfg.database.user;
                    ensureDBOwnership = true;
                  }
                ];
              };
            })

            (lib.mkIf cfg.redis.enable {
              services.redis.servers.mcap-query = {
                enable = true;
                bind = cfg.redis.host;
                port = cfg.redis.port;
              };
            })

            (lib.mkIf cfg.nginx.enable {
              services.nginx.enable = true;
              services.nginx.virtualHosts.${cfg.nginx.serverName} = {
                forceSSL = cfg.nginx.forceSSL;
                enableACME = cfg.nginx.enableACME;
                locations."/api/" = {
                  proxyPass = "http://${cfg.host}:${toString cfg.port}/";
                  proxyWebsockets = true;
                };
                locations."/" = {
                  proxyPass =
                    if cfg.frontend.enable
                    then "http://${cfg.frontend.host}:${toString cfg.frontend.port}"
                    else "http://${cfg.host}:${toString cfg.port}";
                  proxyWebsockets = true;
                };
              };
            })
          ]);
        };

      nixosModules.mcap-query-backend = self.nixosModules.default;
    };
}
