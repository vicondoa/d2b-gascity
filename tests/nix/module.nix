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
      credentials.githubPrivateKeyFile = "/run/secrets/github-key";
    };
  };

  core = (mkEval coreConfig).config;
  main = core.systemd.services.d2b-gascity.serviceConfig;
  coreSupervisorText = core.environment.etc."d2b-gascity/supervisor.toml".text;
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

  invalidPort = (mkEval {
    services.d2bGasCity = {
      enable = true;
      package = testPackage;
      dolt.fixedPort = 8372;
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

  core = assert coreD2bUnits == [ "d2b-gascity" ];
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
    assert main.ExecStartPre == [
      "${testPackage}/bin/d2b-gascity-copilot-provider readiness --selection-path /var/lib/d2b-gascity/config/provider-selection.json"
    ];
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
    assert builtins.elem
      "GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service"
      main.Environment;
    assert builtins.elem "GC_SUPERVISOR_SYSTEMD_SCOPE=system" main.Environment;
    assert builtins.elem
      "/etc/d2b-gascity/supervisor.toml:/var/lib/d2b-gascity/gc/supervisor.toml"
      main.BindReadOnlyPaths;
    assert builtins.elem "copilot-token:/run/secrets/copilot" main.LoadCredential;
    assert builtins.elem
      "github-private-key:/run/secrets/github-key"
      main.LoadCredential;
    assert !(lib.hasInfix "GC_DOLT_PORT=" (stringValue main.Environment));
    assert !(lib.hasInfix "allowed_origins" coreSupervisorText);
    assert !(lib.hasInfix "allow_mutations" coreSupervisorText);
    assert !(lib.hasInfix "write_auth_" coreSupervisorText);
    assert !(lib.hasInfix "read_auth_" coreSupervisorText);
    assert !(core.services.d2bGasCity.supervisor ? bind);
    true;

  "without-copilot" = assert (noCopilotMain.ExecStartPre or [ ]) == [ ];
    true;

  "fixed-port" = assert builtins.elem "GC_DOLT_PORT=8375"
    fixedPortMain.Environment;
    assert lib.hasInfix
      "tcp dport 8375 meta skuid != 41080 drop"
      fixedPort.networking.nftables.ruleset;
    true;

  remote = assert remoteD2bUnits
    == [ "d2b-gascity" "d2b-gascity-relay" "d2b-gascity-tinyauth" ];
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
    assert lib.hasInfix "d2b-gascity-tinyauth.service"
      (stringValue (relayUnit.requires or [ ]));
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
    assert !(lib.hasInfix "$scheme" relayText);
    assert !(lib.hasInfix "$server_port" relayText);
    assert lib.hasInfix "proxy_buffering off" relayText;
    assert lib.hasInfix "allow 127.0.0.1/32;" relayText;
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
    assert lib.hasInfix "table inet d2b_gascity" remote.networking.nftables.ruleset;
    assert lib.hasInfix "tcp dport 8373 ip saddr !="
      remote.networking.nftables.ruleset;
    assert lib.hasInfix "tcp dport 8374 ip saddr !="
      remote.networking.nftables.ruleset;
    assert lib.hasInfix "tcp dport 8375 meta skuid != 41081 drop"
      remote.networking.nftables.ruleset;
    assert lib.hasInfix "tcp dport 8372 meta skuid != { 41080, 41081 } drop"
      remote.networking.nftables.ruleset;
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

  "invalid-port" = assert hasFailedAssertion "ports" invalidPort.assertions;
    true;

  "invalid-remote-host" = assert hasFailedAssertion
    "must be distinct"
    invalidRemoteHost.assertions;
    true;

  "invalid-auth-scope" = assert hasFailedAssertion
    "must be a subdomain"
    invalidAuthScope.assertions;
    true;

  "invalid-remote-port" = assert hasFailedAssertion
    "ports"
    invalidRemotePort.assertions;
    true;

  "invalid-relay-address" = assert hasFailedAssertion
    "relayAddress"
    invalidRelayAddress.assertions;
    true;

  "invalid-paths" = assert lib.all
    (candidate: hasFailedAssertion "copilotTokenFile" candidate.assertions)
    invalidPathConfigs;
    true;
}
