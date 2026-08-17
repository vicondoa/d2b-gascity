{ lib
, nixpkgs
, pkgs
, module
}:

let
  system = pkgs.stdenv.hostPlatform.system;
  testPackage = pkgs.hello // {
    passthru = (pkgs.hello.passthru or { }) // {
      tinyauth = pkgs.hello;
      nginx = pkgs.hello;
    };
  };

  base = {
    system.stateVersion = "25.11";
    users.users.alice = {
      isNormalUser = true;
      uid = 1000;
    };
  };

  mkEval = extra:
    nixpkgs.lib.nixosSystem {
      inherit system;
      modules = [
        base
        module
        extra
      ];
    };

  disabled = (mkEval { }).config;

  coreConfig = {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      operators.users = [ "alice" ];
      credentials.copilotTokenFile = "/run/secrets/copilot";
      credentials.githubPublicationTokenFile = "/run/secrets/github-publication-token";
      credentials.githubPublicationPolicyFile = "/run/secrets/github-publication-policy";
    };
  };

  core = (mkEval coreConfig).config;
  main = core.systemd.services.d2b-gascity.serviceConfig;
  apiProxy = core.systemd.services.d2b-gascity-api-proxy.serviceConfig;
  apiProxySocket = core.systemd.sockets.d2b-gascity-api-proxy;
  coreSupervisorText = core.environment.etc."d2b-gascity/supervisor.toml".text;
  appAuthConfig = {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      credentials.githubPublicationPolicyFile = "/run/secrets/github-publication-policy";
      credentials.githubPublicationAppKeyFile = "/run/secrets/github-publication-app-key";
      credentials.githubPublicationAppConfigFile = "/run/secrets/github-publication-app-config";
    };
  };

  appAuth = (mkEval appAuthConfig).config;
  appMain = appAuth.systemd.services.d2b-gascity.serviceConfig;
  invalidFirewallDisabled = (mkEval {
    networking.firewall.enable = false;
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
    };
  }).config;
  invalidNftablesBackend = (mkEval {
    networking.firewall.backend = "nftables";
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
    };
  }).config;
  noCopilot = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
    };
  }).config;
  noCopilotMain = noCopilot.systemd.services.d2b-gascity.serviceConfig;
  coreD2bUnits = builtins.filter
    (name: lib.hasPrefix "d2b-gascity" name)
    (builtins.attrNames core.systemd.services);

  fixedPort = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dolt.fixedPort = 8375;
    };
  }).config;
  fixedPortMain = fixedPort.systemd.services.d2b-gascity.serviceConfig;

  invalidApiProxyPort = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dolt.fixedPort = 18372;
    };
  }).config;

  remoteConfig = {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      operators.users = [ "alice" ];
      dashboard.remote = {
        enable = true;
        relayAddress = "127.0.0.1";
        relayInterface = "lo";
        relayPort = 8373;
        authPort = 8374;
        tinyauthPort = 8375;
        hostname = "gascity.example.test";
        authHostname = "auth.gascity.example.test";
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  };

  remote = (mkEval remoteConfig).config;
  relayUnit = remote.systemd.services.d2b-gascity-relay;
  tinyauthUnit = remote.systemd.services.d2b-gascity-tinyauth;
  relay = remote.systemd.services.d2b-gascity-relay.serviceConfig;
  tinyauth = remote.systemd.services.d2b-gascity-tinyauth.serviceConfig;
  relayText = remote.environment.etc."d2b-gascity/relay.conf".text;
  relayFlat = lib.replaceStrings [ "\n" ] [ " " ] relayText;
  tinyauthText = remote.environment.etc."d2b-gascity/tinyauth.yml".text;
  remoteSupervisorText =
    remote.environment.etc."d2b-gascity/supervisor.toml".text;
  remoteD2bUnits = builtins.filter
    (name: lib.hasPrefix "d2b-gascity" name)
    (builtins.attrNames remote.systemd.services);

  invalidRemote = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote.enable = true;
    };
  }).config;

  invalidRelayAddress = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote = {
        enable = true;
        relayAddress = "0.0.0.0";
        hostname = "gascity.example.test";
        authHostname = "auth.gascity.example.test";
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  }).config;

  invalidRemoteHost = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote = {
        enable = true;
        hostname = "same.example.test";
        authHostname = "same.example.test";
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  }).config;

  invalidAuthScope = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote = {
        enable = true;
        hostname = "gascity.example.test";
        authHostname = "auth.example.test";
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  }).config;

  invalidNestedAuth = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote = {
        enable = true;
        hostname = "gascity.example.test";
        authHostname = "auth.ops.gascity.example.test";
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  }).config;

  invalidRemotePort = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dashboard.remote = {
        enable = true;
        hostname = "gascity.example.test";
        authHostname = "auth.example.test";
        authPort = 8372;
        trustedExternalProxyCidrs = [ "127.0.0.1/32" ];
        tinyauthUsersFile = "/run/secrets/gascity-users";
      };
    };
  }).config;

  invalidPath = path: (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      credentials.copilotTokenFile = path;
    };
  }).config;

  invalidPathConfigs = map invalidPath [
    "/"
    "/run//secrets/copilot"
    "/run/../secrets/copilot"
    "/nix/store/secret"
    "relative/copilot"
    "/run/secrets/copilot\nnext"
  ];

  invalidPublicationNoPolicy = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      credentials.githubPublicationAppKeyFile = "/run/secrets/github-publication-app-key";
      credentials.githubPublicationAppConfigFile = "/run/secrets/github-publication-app-config";
    };
  }).config;

  invalidPublicationPartial = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      credentials.githubPublicationPolicyFile = "/run/secrets/github-publication-policy";
      credentials.githubPublicationAppKeyFile = "/run/secrets/github-publication-app-key";
    };
  }).config;

  invalidPublicationBoth = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      credentials.githubPublicationPolicyFile = "/run/secrets/github-publication-policy";
      credentials.githubPublicationTokenFile = "/run/secrets/github-publication-token";
      credentials.githubPublicationAppKeyFile = "/run/secrets/github-publication-app-key";
      credentials.githubPublicationAppConfigFile = "/run/secrets/github-publication-app-config";
    };
  }).config;

  hasFailedAssertion = needle: assertions:
    lib.any (
      assertion:
      !(assertion.assertion) && lib.hasInfix needle assertion.message
    ) assertions;

  stringValue = value:
    if builtins.isList value then
      lib.concatStringsSep "\n" value
    else
      value;

  environmentValue = name: environment:
    let
      entries = builtins.filter
        (entry: lib.hasPrefix "${name}=" entry)
        environment;
    in
    assert lib.length entries == 1;
    builtins.head (builtins.match "${name}=(.*)" (builtins.head entries));

  coreGcHome = environmentValue "GC_HOME" main.Environment;
  coreDoltRoot = environmentValue "DOLT_ROOT_PATH" main.Environment;
  coreGitConfig = environmentValue "GIT_CONFIG_GLOBAL" main.Environment;
in
{
  _relayConfig = relayText;

  disabled = assert !(disabled.systemd.services ? d2b-gascity);
    assert !(disabled.users.users ? d2b-gascity);
    assert !(lib.any
      (rule: lib.hasInfix "d2b-gascity" rule)
      (disabled.systemd.tmpfiles.rules or [ ]));
    assert !(disabled.environment.etc ? "d2b-gascity/supervisor.toml");
    assert !(disabled.networking.nftables.enable or false);
    assert !(disabled.networking.firewall.interfaces ? lo);
    true;

  core = assert coreD2bUnits
    == [ "d2b-gascity" "d2b-gascity-api-proxy" ];
    assert core.networking.firewall.enable;
    assert core.networking.firewall.backend == "iptables";
    assert !(core.networking.nftables.enable or false);
    assert (core.networking.nftables.ruleset or "") == "";
    assert lib.hasInfix "destroy table inet d2b_gascity"
      core.networking.firewall.extraCommands;
    assert !(lib.hasInfix "delete table"
      core.networking.firewall.extraCommands);
    assert lib.hasInfix "/bin/nft -f -"
      core.networking.firewall.extraCommands;
    assert lib.length (lib.splitString "/bin/nft -f -"
      core.networking.firewall.extraCommands) == 2;
    assert lib.hasInfix "table inet d2b_gascity"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix "chain input {"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix "type filter hook input priority 0; policy accept;"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix "chain output {"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix "type filter hook output priority 0; policy accept;"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix "tcp dport 8372 meta skuid != { 41080 } drop"
      core.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 18372 meta skuid != 41080 drop"
      core.networking.firewall.extraCommands;
    assert !(lib.hasInfix "iifname"
      core.networking.firewall.extraCommands);
    assert (core.networking.firewall.extraStopCommands or "") == "";
    assert !(lib.hasInfix "flush ruleset"
      core.networking.firewall.extraCommands);
    assert main.ExecStart == "${testPackage}/bin/gc supervisor run";
    assert main.User == "d2b-gascity";
    assert main.Group == "d2b-gascity";
    assert main.KillMode == "control-group";
    assert main.StateDirectory == "d2b-gascity";
    assert main.StateDirectoryMode == "0750";
    assert main.CPUQuota == "100%";
    assert main.MemoryHigh == "2G";
    assert main.MemoryMax == "4G";
    assert main.MemorySwapMax == "0";
    assert main.TasksMax == 512;
    assert builtins.length main.ExecStartPre == 2;
    assert lib.hasInfix "d2b-gascity-tmux-start" (builtins.toString main.ExecStartPre);
    assert lib.hasInfix
      "d2b-gascity-copilot-provider readiness --selection-path /var/lib/d2b-gascity/config/provider-selection.json"
      (builtins.toString main.ExecStartPre);
    assert lib.hasInfix "d2b-gascity-tmux-stop" (builtins.toString main.ExecStopPost);
    assert main.NoNewPrivileges;
    assert main.PrivateTmp;
    assert main.PrivateDevices;
    assert main.ProtectHome;
    assert main.ProtectSystem == "strict";
    assert main.ProtectKernelTunables;
    assert main.ProtectKernelModules;
    assert main.ProtectKernelLogs;
    assert main.ProtectControlGroups;
    assert main.RestrictSUIDSGID;
    assert main.LockPersonality;
    assert main.AmbientCapabilities == [ "" ];
    assert main.CapabilityBoundingSet == [ "" ];
    assert main.RestrictAddressFamilies == [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    assert core.users.groups.d2b-gascity-operators.members == [ "alice" ];
    assert (main.SystemCallFilter or null) == null;
    assert builtins.elem "GC_HOME=/var/lib/d2b-gascity/gc" main.Environment;
    assert coreGcHome == "/var/lib/d2b-gascity/gc";
    assert coreDoltRoot == "${coreGcHome}/dolt";
    assert coreGitConfig == "${coreGcHome}/gitconfig";
    assert builtins.elem
      "GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service"
      main.Environment;
    assert builtins.elem "GC_SUPERVISOR_SYSTEMD_SCOPE=system" main.Environment;
    assert builtins.elem
      "TMPDIR=/tmp"
      main.Environment;
    assert builtins.elem
      "TMUX_TMPDIR=/run/d2b-gascity"
      main.Environment;
    assert builtins.elem
      "/etc/d2b-gascity/supervisor.toml:/var/lib/d2b-gascity/gc/supervisor.toml"
      main.BindReadOnlyPaths;
    assert builtins.elem "copilot-token:/run/secrets/copilot" main.LoadCredential;
    assert builtins.elem
      "github-publication-token:/run/secrets/github-publication-token"
      main.LoadCredential;
    assert builtins.elem
      "github-publication-policy:/run/secrets/github-publication-policy"
      main.LoadCredential;
    assert builtins.elem
      "PATH=${testPackage}/bin:${pkgs.openssl}/bin:/run/current-system/sw/bin"
      main.Environment;
    assert !(lib.hasInfix "GC_DOLT_PORT=" (stringValue main.Environment));
    assert !(lib.hasInfix "allowed_origins" coreSupervisorText);
    assert !(lib.hasInfix "allow_mutations" coreSupervisorText);
    assert !(lib.hasInfix "write_auth_" coreSupervisorText);
    assert !(lib.hasInfix "read_auth_" coreSupervisorText);
    assert !(core.services.d2bGasCity ? supervisor);
    assert lib.hasInfix "bind = \"127.0.0.1\"" coreSupervisorText;
    assert lib.hasInfix "port = 8372" coreSupervisorText;
    assert apiProxy.ExecStart
      == "${pkgs.systemd}/lib/systemd/systemd-socket-proxyd 127.0.0.1:8372";
    assert apiProxy.User == "d2b-gascity";
    assert apiProxy.Group == "d2b-gascity";
    assert apiProxy.Restart == "on-failure";
    assert apiProxy.KillMode == "control-group";
    assert apiProxy.NoNewPrivileges;
    assert apiProxy.PrivateTmp;
    assert apiProxy.PrivateDevices;
    assert apiProxy.ProtectHome;
    assert apiProxy.ProtectSystem == "strict";
    assert apiProxy.ProtectKernelTunables;
    assert apiProxy.ProtectKernelModules;
    assert apiProxy.ProtectKernelLogs;
    assert apiProxy.ProtectKernelKeyring;
    assert apiProxy.ProtectControlGroups;
    assert apiProxy.ProtectClock;
    assert apiProxy.ProtectHostname;
    assert apiProxy.ProtectProc == "invisible";
    assert apiProxy.ProcSubset == "pid";
    assert apiProxy.RestrictSUIDSGID;
    assert apiProxy.LockPersonality;
    assert apiProxy.UMask == "0077";
    assert apiProxy.AmbientCapabilities == [ "" ];
    assert apiProxy.CapabilityBoundingSet == [ "" ];
    assert apiProxy.RestrictAddressFamilies
      == [ "AF_UNIX" "AF_INET" "AF_INET6" ];
    assert apiProxySocket.listenStreams == [ "127.0.0.1:18372" ];
    assert apiProxySocket.wantedBy == [ "sockets.target" ];
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (apiProxy.requires or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (apiProxy.wants or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (apiProxy.after or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (apiProxy.bindsTo or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (apiProxy.partOf or [ ])));
    assert (apiProxySocket.unitConfig.PartOf or null) == null;
    true;

  "app-auth" = assert builtins.elem
    "github-publication-app-key:/run/secrets/github-publication-app-key"
    appMain.LoadCredential;
    assert builtins.elem
      "github-publication-app-config:/run/secrets/github-publication-app-config"
      appMain.LoadCredential;
    assert builtins.elem
      "github-publication-policy:/run/secrets/github-publication-policy"
      appMain.LoadCredential;
    assert !(builtins.elem
      "github-publication-token:/run/secrets/github-publication-token"
      appMain.LoadCredential);
    true;

  "without-copilot" = assert builtins.length (noCopilotMain.ExecStartPre or [ ]) == 1;
    assert lib.hasInfix
      "d2b-gascity-tmux-start"
      (builtins.toString noCopilotMain.ExecStartPre);
    true;

  "fixed-port" = assert builtins.elem "GC_DOLT_PORT=8375"
    fixedPortMain.Environment;
    assert !(fixedPort.networking.nftables.enable or false);
    assert (fixedPort.networking.nftables.ruleset or "") == "";
    assert fixedPort.networking.firewall.backend == "iptables";
    assert lib.hasInfix
      "tcp dport 8375 meta skuid != 41080 drop"
      fixedPort.networking.firewall.extraCommands;
    assert (fixedPort.networking.firewall.extraStopCommands or "") == "";
    true;

  remote = assert remoteD2bUnits
    == [
      "d2b-gascity"
      "d2b-gascity-api-proxy"
      "d2b-gascity-relay"
      "d2b-gascity-tinyauth"
    ];
    assert (remote.systemd.services.d2b-gascity-relay.unitConfig.PartOf or null) == null;
    assert (remote.systemd.services.d2b-gascity-tinyauth.unitConfig.PartOf or null) == null;
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (relay.Requires or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (tinyauth.Requires or [ ])));
    assert builtins.elem
      "users:/run/secrets/gascity-users"
      tinyauth.LoadCredential;
    assert tinyauth.StateDirectory == "d2b-gascity-tinyauth";
    assert tinyauth.StateDirectoryMode == "0750";
    assert tinyauth.WorkingDirectory == "/var/lib/d2b-gascity-tinyauth";
    assert tinyauth.MemoryHigh == "256M";
    assert tinyauth.MemoryMax == "512M";
    assert relay.CPUQuota == "50%";
    assert relay.TasksMax == 128;
    assert !(lib.hasInfix "d2b-gascity-tinyauth.service"
      (stringValue (relayUnit.requires or [ ])));
    assert lib.hasInfix "d2b-gascity-tinyauth.service"
      (stringValue (relayUnit.wants or [ ]));
    assert lib.hasInfix "d2b-gascity-tinyauth.service"
      (stringValue (relayUnit.after or [ ]));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (relayUnit.requires or [ ])));
    assert !(lib.hasInfix "d2b-gascity.service"
      (stringValue (tinyauthUnit.requires or [ ])));
    assert lib.hasInfix "listen 127.0.0.1:8374" relayText;
    assert lib.hasInfix "server_name auth.gascity.example.test" relayText;
    assert lib.hasInfix "listen 127.0.0.1:8373" relayText;
    assert lib.hasInfix "server_name gascity.example.test" relayText;
    assert lib.hasInfix "127.0.0.1:8375" relayText;
    assert lib.hasInfix "auth_request /_d2b_tinyauth" relayText;
    assert lib.hasInfix "proxy_pass http://127.0.0.1:8372;" relayText;
    assert lib.hasInfix "proxy_pass_request_body on" relayText;
    assert lib.hasInfix "limit_req_status 429" relayText;
    assert lib.hasInfix "map $request_uri $d2b_forwarded_uri" relayText;
    assert lib.hasInfix "proxy_set_header Host $http_host" relayText;
    assert lib.hasInfix "proxy_set_header Host auth.gascity.example.test" relayText;
    assert lib.hasInfix
      "proxy_set_header X-Forwarded-Host gascity.example.test"
      relayText;
    assert lib.hasInfix "proxy_set_header X-Forwarded-Port 443" relayText;
    assert lib.hasInfix "proxy_set_header X-Forwarded-Proto https" relayText;
    assert lib.hasInfix
      "proxy_set_header X-Forwarded-For $remote_addr"
      relayText;
    assert lib.hasInfix
      "proxy_set_header X-Real-IP $remote_addr"
      relayText;
    assert lib.hasInfix "proxy_set_header Origin $http_origin" relayText;
    assert lib.hasInfix
      "proxy_set_header Sec-Fetch-Site $http_sec_fetch_site"
      relayText;
    assert lib.hasInfix "proxy_set_header X-GC-Request $http_x_gc_request" relayText;
    assert lib.hasInfix "proxy_set_header Last-Event-ID $http_last_event_id" relayText;
    assert lib.hasInfix
      "auth_request_set $tinyauth_set_cookie $upstream_http_set_cookie"
      relayText;
    assert lib.hasInfix
      "add_header Set-Cookie $tinyauth_set_cookie always"
      relayText;
    assert lib.hasInfix "return 302 $tinyauth_location" relayText;
    assert lib.hasInfix "d2b_dashboard_mutation_denied" relayText;
    assert lib.hasInfix "d2b_auth_mutation_denied" relayText;
    assert lib.hasInfix "geo $d2b_source_admitted" relayText;
    assert lib.hasInfix "if ($d2b_source_admitted = 0) { return 403; }"
      relayText;
    assert lib.hasInfix "d2b_auth_bad_origin" relayText;
    assert lib.hasInfix "d2b_auth_bad_referer" relayText;
    assert builtins.match
      ".*map \\$http_origin \\$d2b_auth_bad_origin \\{[[:space:]]+default 1;[[:space:]]+\"\" 0;[[:space:]]+\"https://auth\\.gascity\\.example\\.test\" 0;.*"
      relayFlat != null;
    assert !(lib.hasInfix "$scheme" relayText);
    assert !(lib.hasInfix "$server_port" relayText);
    assert lib.hasInfix "proxy_buffering off" relayText;
    assert lib.hasInfix "allow 127.0.0.1/32;" relayText;
    assert lib.hasInfix "deny all;" relayText;
    assert builtins.elem 8373
      remote.networking.firewall.interfaces.lo.allowedTCPPorts;
    assert builtins.elem 8374
      remote.networking.firewall.interfaces.lo.allowedTCPPorts;
    assert lib.hasInfix
      "GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service"
      (stringValue remote.systemd.services.d2b-gascity.serviceConfig.Environment);
    assert lib.hasInfix
      "allowed_hosts = [\"gascity.example.test\"]"
      remoteSupervisorText;
    assert lib.hasInfix "port = 8372" remoteSupervisorText;
    assert lib.hasInfix "appurl: https://auth.gascity.example.test" tinyauthText;
    assert lib.hasInfix "subdomainsenabled: true" tinyauthText;
    assert lib.hasInfix "driver: sqlite" tinyauthText;
    assert lib.hasInfix
      "path: /var/lib/d2b-gascity-tinyauth/tinyauth.db"
      tinyauthText;
    assert !(remote.services.d2bGasCity.dashboard.remote ? externalScheme);
    assert !(lib.hasInfix "allowed_origins" remoteSupervisorText);
    assert !(lib.hasInfix "allow_mutations" remoteSupervisorText);
    assert !(lib.hasInfix "write_auth_" remoteSupervisorText);
    assert !(lib.hasInfix "read_auth_" remoteSupervisorText);
    assert !(remote.networking.nftables.enable or false);
    assert (remote.networking.nftables.ruleset or "") == "";
    assert remote.networking.firewall.enable;
    assert remote.networking.firewall.backend == "iptables";
    assert lib.hasInfix "/bin/nft -f -"
      remote.networking.firewall.extraCommands;
    assert lib.length (lib.splitString "/bin/nft -f -"
      remote.networking.firewall.extraCommands) == 2;
    assert lib.hasInfix "destroy table inet d2b_gascity"
      remote.networking.firewall.extraCommands;
    assert !(lib.hasInfix "delete table"
      remote.networking.firewall.extraCommands);
    assert lib.hasInfix "table inet d2b_gascity"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 8373 ip saddr != { 127.0.0.1/32 } drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 8373 ip6 saddr != { ::/128 } drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 8374 ip saddr != { 127.0.0.1/32 } drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 8374 ip6 saddr != { ::/128 } drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix "tcp dport 8375 meta skuid != 41081 drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix "tcp dport 8372 meta skuid != { 41080, 41081 } drop"
      remote.networking.firewall.extraCommands;
    assert lib.hasInfix
      "tcp dport 18372 meta skuid != 41080 drop"
      remote.networking.firewall.extraCommands;
    assert (remote.networking.firewall.extraStopCommands or "") == "";
    assert !(lib.hasInfix "flush ruleset"
      remote.networking.firewall.extraCommands);
    true;

  "invalid-firewall-disabled" = assert hasFailedAssertion
    "firewall.enable = true"
    invalidFirewallDisabled.assertions;
    true;

  "invalid-nftables-backend" = assert hasFailedAssertion
    "firewall.backend = \"iptables\""
    invalidNftablesBackend.assertions;
    true;

  "invalid-remote" = assert hasFailedAssertion
    "trustedExternalProxyCidrs"
    invalidRemote.assertions;
    assert hasFailedAssertion "dashboard.remote.hostname"
      invalidRemote.assertions;
    assert hasFailedAssertion "dashboard.remote.authHostname"
      invalidRemote.assertions;
    assert hasFailedAssertion "tinyauthUsersFile" invalidRemote.assertions;
    true;

  "invalid-remote-host" = assert hasFailedAssertion
    "must be distinct"
    invalidRemoteHost.assertions;
    true;

  "invalid-auth-scope" = assert hasFailedAssertion
    "must be a subdomain"
    invalidAuthScope.assertions;
    true;

  "invalid-nested-auth" = assert hasFailedAssertion
    "exactly one additional label"
    invalidNestedAuth.assertions;
    true;

  "invalid-remote-port" = assert hasFailedAssertion
    "ports"
    invalidRemotePort.assertions;
    true;

  "invalid-api-proxy-port" = assert hasFailedAssertion
    "ports"
    invalidApiProxyPort.assertions;
    true;

  "invalid-relay-address" = assert hasFailedAssertion
    "relayAddress"
    invalidRelayAddress.assertions;
    true;

  "invalid-paths" = assert lib.all
    (candidate: hasFailedAssertion "copilotTokenFile" candidate.assertions)
    invalidPathConfigs;
    true;

  "invalid-publication-no-policy" = assert hasFailedAssertion
    "githubPublicationPolicyFile is required"
    invalidPublicationNoPolicy.assertions;
    true;

  "invalid-publication-partial" = assert hasFailedAssertion
    "must be configured together"
    invalidPublicationPartial.assertions;
    assert hasFailedAssertion "exactly one GitHub publication auth mode"
      invalidPublicationPartial.assertions;
    true;

  "invalid-publication-both" = assert hasFailedAssertion
    "exactly one GitHub publication auth mode"
    invalidPublicationBoth.assertions;
    true;
}
