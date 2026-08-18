{ config, lib, pkgs, ... }:

let
  cfg = config.services.d2bGasCity;
  remote = cfg.dashboard.remote;

  packagePassthru =
    if cfg.package == null then
      { }
    else
      (cfg.package.passthru or { });

  resolvePackage = override: name:
    if override != null then
      override
    else
      lib.attrByPath [ name ] pkgs.hello packagePassthru;

  tinyauth = resolvePackage remote.tinyauthPackage "tinyauth";
  nginx = resolvePackage remote.nginxPackage "nginx";
  relayAddress =
    if lib.hasInfix ":" remote.relayAddress then
      "[${remote.relayAddress}]"
    else
      remote.relayAddress;
  nginxAllows = lib.concatMapStringsSep "\n"
    (cidr: "        allow ${cidr};")
    remote.trustedExternalProxyCidrs;
  nginxSourceAdmission = lib.concatMapStringsSep "\n"
    (cidr: "        ${cidr} 1;")
    remote.trustedExternalProxyCidrs;
  authHostnameRegex = lib.escapeRegex remote.authHostname;
  tinyAuthCredentialPath =
    "/run/credentials/d2b-gascity-tinyauth.service/users";
  tinyAuthStateRoot = "/var/lib/d2b-gascity-tinyauth";

  tinyauthConfigText = ''
    appurl: https://${remote.authHostname}
    server:
      address: 127.0.0.1
      port: ${toString remote.tinyauthPort}
    auth:
      usersfile: ${tinyAuthCredentialPath}
      securecookie: true
      subdomainsenabled: true
      sessionexpiry: 3600
      sessionmaxlifetime: 86400
      loginmaxretries: 3
      logintimeout: 300
      trustedproxies: 127.0.0.1/32
    database:
      driver: sqlite
      path: ${tinyAuthStateRoot}/tinyauth.db
    analytics:
      enabled: false
    log:
      level: warn
  '';

  nginxConfigText = ''
    worker_processes 1;
    pid ${"/run/d2b-gascity-relay/nginx.pid"};
    error_log stderr warn;
    events {
      worker_connections 256;
    }
    http {
      access_log off;

      geo $d2b_source_admitted {
        default 0;
${nginxSourceAdmission}
      }
      map $http_upgrade $d2b_connection_upgrade {
        default upgrade;
        "" close;
      }
      map $request_method $d2b_unsafe_method {
        default 0;
        POST 1;
        PUT 1;
        PATCH 1;
        DELETE 1;
      }
      map $http_origin $d2b_dashboard_origin_ok {
        default 0;
        "https://${remote.hostname}" 1;
      }
      map $http_origin $d2b_dashboard_origin_present {
        default 1;
        "" 0;
      }
      map $request_uri $d2b_forwarded_uri {
        default $request_uri;
        ~^(?<d2b_path>[^?]+)\?(?<d2b_query>.*)$ $d2b_path%3F$d2b_query;
      }
      map $http_sec_fetch_site $d2b_dashboard_fetch_ok {
        default 0;
        same-origin 1;
      }
      map "$d2b_unsafe_method:$d2b_dashboard_origin_ok:$d2b_dashboard_fetch_ok" $d2b_dashboard_mutation_denied {
        default 0;
        ~^1:0 1;
        ~^1:1:0 1;
      }
      map $http_origin $d2b_auth_bad_origin {
        default 1;
        "" 0;
        "https://${remote.authHostname}" 0;
      }
      map $http_referer $d2b_auth_bad_referer {
        default 1;
        "" 0;
        ~^https://${authHostnameRegex}(/|\?|$) 0;
      }
      map $http_origin $d2b_auth_origin_present {
        default 1;
        "" 0;
      }
      map $http_referer $d2b_auth_referer_present {
        default 1;
        "" 0;
      }
      map "$d2b_unsafe_method:$d2b_auth_origin_present:$d2b_auth_bad_origin:$d2b_auth_referer_present:$d2b_auth_bad_referer" $d2b_auth_mutation_denied {
        default 0;
        ~^1:1:1 1;
        ~^1:0:0:0 1;
        ~^1:0:0:1:1 1;
      }
      map $uri $d2b_tinyauth_login_limit_key {
        default "";
        /api/user/login $binary_remote_addr;
      }
      limit_req_zone $d2b_tinyauth_login_limit_key zone=d2b_tinyauth_login:10m rate=5r/m;
      limit_req_status 429;

      server {
        listen ${relayAddress}:${toString remote.authPort};
        server_name ${remote.authHostname};
${nginxAllows}
        if ($d2b_source_admitted = 0) { return 403; }
        deny all;
        if ($http_host != "${remote.authHostname}") { return 421; }
        if ($d2b_auth_mutation_denied = 1) { return 403; }

        location / {
          limit_req zone=d2b_tinyauth_login burst=10 nodelay;
          proxy_pass http://127.0.0.1:${toString remote.tinyauthPort};
          proxy_http_version 1.1;
          proxy_pass_request_body on;
          proxy_set_header Host ${remote.authHostname};
          proxy_set_header Origin $http_origin;
          proxy_set_header Referer $http_referer;
          proxy_set_header Cookie $http_cookie;
          proxy_set_header X-Forwarded-Host ${remote.authHostname};
          proxy_set_header X-Forwarded-Port 443;
          proxy_set_header X-Forwarded-Proto https;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-Uri $d2b_forwarded_uri;
          proxy_set_header X-Original-URI $d2b_forwarded_uri;
          proxy_set_header Authorization "";
          proxy_set_header Remote-User "";
          proxy_set_header X-Remote-User "";
          proxy_set_header X-Auth-Request-User "";
          proxy_set_header X-Forwarded-User "";
          proxy_set_header X-Original-User "";
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection $d2b_connection_upgrade;
          proxy_request_buffering off;
          proxy_buffering off;
          proxy_cache off;
          proxy_connect_timeout 2s;
          proxy_read_timeout 30s;
          proxy_send_timeout 30s;
          proxy_next_upstream off;
        }
      }

      server {
        listen ${relayAddress}:${toString remote.relayPort};
        server_name ${remote.hostname};
${nginxAllows}
        if ($d2b_source_admitted = 0) { return 403; }
        deny all;
        if ($http_host != "${remote.hostname}") { return 421; }
        if ($d2b_dashboard_mutation_denied = 1) { return 403; }

        location = /_d2b_tinyauth {
          internal;
          proxy_pass http://127.0.0.1:${toString remote.tinyauthPort}/api/auth/nginx;
          proxy_http_version 1.1;
          proxy_pass_request_body off;
          proxy_set_header Content-Length "";
          proxy_set_header Host ${remote.authHostname};
          proxy_set_header Origin $http_origin;
          proxy_set_header Referer $http_referer;
          proxy_set_header Cookie $http_cookie;
          proxy_set_header X-Forwarded-Host ${remote.hostname};
          proxy_set_header X-Forwarded-Port 443;
          proxy_set_header X-Forwarded-Proto https;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-Uri $d2b_forwarded_uri;
          proxy_set_header X-Original-URI $d2b_forwarded_uri;
          proxy_set_header Authorization "";
          proxy_set_header Remote-User "";
          proxy_set_header X-Remote-User "";
          proxy_set_header X-Auth-Request-User "";
          proxy_set_header X-Forwarded-User "";
          proxy_set_header X-Original-User "";
          proxy_buffering off;
          proxy_cache off;
          proxy_connect_timeout 2s;
          proxy_read_timeout 3s;
          proxy_send_timeout 3s;
          proxy_next_upstream off;
        }

        location / {
          auth_request /_d2b_tinyauth;
          auth_request_set $tinyauth_location $upstream_http_x_tinyauth_location;
          auth_request_set $tinyauth_set_cookie $upstream_http_set_cookie;
          add_header Set-Cookie $tinyauth_set_cookie always;
          error_page 401 = @tinyauth_login;

          proxy_pass http://127.0.0.1:8372;
          proxy_http_version 1.1;
          proxy_pass_request_body on;
          proxy_set_header Host $http_host;
          proxy_set_header Origin $http_origin;
          proxy_set_header Referer $http_referer;
          proxy_set_header Sec-Fetch-Site $http_sec_fetch_site;
          proxy_set_header X-GC-Request $http_x_gc_request;
          proxy_set_header Last-Event-ID $http_last_event_id;
          proxy_set_header Cookie $http_cookie;
          proxy_set_header X-Forwarded-Host ${remote.hostname};
          proxy_set_header X-Forwarded-Port 443;
          proxy_set_header X-Forwarded-Proto https;
          proxy_set_header X-Forwarded-For $remote_addr;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header Authorization "";
          proxy_set_header Remote-User "";
          proxy_set_header X-Remote-User "";
          proxy_set_header X-Auth-Request-User "";
          proxy_set_header X-User "";
          proxy_set_header X-Authenticated-User "";
          proxy_set_header X-Forwarded-User "";
          proxy_set_header X-Original-User "";
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection $d2b_connection_upgrade;
          proxy_buffering off;
          proxy_request_buffering off;
          proxy_read_timeout 3600s;
          proxy_send_timeout 3600s;
          proxy_next_upstream off;
          add_header X-Accel-Buffering no always;
        }

        location @tinyauth_login {
          add_header Set-Cookie $tinyauth_set_cookie always;
          return 302 $tinyauth_location;
        }
      }
    }
  '';

  commonSandbox = {
    Type = "exec";
    PrivateTmp = true;
    PrivateDevices = true;
    ProtectHome = true;
    ProtectSystem = "strict";
    ProtectKernelTunables = true;
    ProtectKernelModules = true;
    ProtectKernelLogs = true;
    ProtectKernelKeyring = true;
    ProtectControlGroups = true;
    ProtectClock = true;
    ProtectHostname = true;
    ProtectProc = "invisible";
    ProcSubset = "pid";
    NoNewPrivileges = true;
    AmbientCapabilities = [ "" ];
    CapabilityBoundingSet = [ "" ];
    RestrictSUIDSGID = true;
    LockPersonality = true;
    UMask = "0077";
    RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    Restart = "on-failure";
    RestartSec = "5s";
    CPUQuota = "50%";
    MemoryHigh = "256M";
    MemoryMax = "512M";
    TasksMax = 128;
    TimeoutStartSec = "30s";
    TimeoutStopSec = "30s";
    LimitNOFILE = 4096;
    KillMode = "control-group";
  };

in
{
  config = lib.mkIf (cfg.enable && remote.enable) {
    users.groups.d2b-gascity-relay = { };
    users.groups.d2b-gascity-tinyauth = { };
    users.users.d2b-gascity-relay = {
      uid = 41081;
      isSystemUser = true;
      group = "d2b-gascity-relay";
      home = "/var/empty";
      createHome = false;
      description = "Gas City authenticated dashboard relay";
    };
    users.users.d2b-gascity-tinyauth = {
      uid = 41082;
      isSystemUser = true;
      group = "d2b-gascity-tinyauth";
      home = "/var/empty";
      createHome = false;
      description = "Gas City TinyAuth endpoint";
    };

    environment.etc."d2b-gascity/tinyauth.yml" = {
      text = tinyauthConfigText;
      mode = "0444";
    };
    environment.etc."d2b-gascity/relay.conf" = {
      text = nginxConfigText;
      mode = "0444";
    };

    systemd.services.d2b-gascity-tinyauth = {
      description = "Gas City TinyAuth ingress infrastructure";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];
      serviceConfig = commonSandbox // {
        User = "d2b-gascity-tinyauth";
        Group = "d2b-gascity-tinyauth";
        StateDirectory = "d2b-gascity-tinyauth";
        StateDirectoryMode = "0750";
        WorkingDirectory = tinyAuthStateRoot;
        RuntimeDirectory = "d2b-gascity-tinyauth";
        RuntimeDirectoryMode = "0750";
        ReadWritePaths = [
          tinyAuthStateRoot
          "/run/d2b-gascity-tinyauth"
        ];
        ExecStart =
          "${tinyauth}/bin/tinyauth --configfile /etc/d2b-gascity/tinyauth.yml";
        LoadCredential = [
          "users:${remote.tinyauthUsersFile}"
        ];
      };
    };

    systemd.services.d2b-gascity-relay = {
      description = "Gas City authenticated dashboard relay";
      wantedBy = [ "multi-user.target" ];
      wants = [ "d2b-gascity-tinyauth.service" ];
      after = [ "d2b-gascity-tinyauth.service" ];
      serviceConfig = commonSandbox // {
        User = "d2b-gascity-relay";
        Group = "d2b-gascity-relay";
        RuntimeDirectory = "d2b-gascity-relay";
        RuntimeDirectoryMode = "0750";
        ReadWritePaths = [ "/run/d2b-gascity-relay" ];
        ExecStart =
          "${nginx}/bin/nginx -p /run/d2b-gascity-relay -c /etc/d2b-gascity/relay.conf -g 'daemon off;'";
      };
    };
  };
}
