{ config, lib, pkgs, ... }:

let
  cfg = config.services.d2bGasCity;
  stateRoot = "/var/lib/d2b-gascity";
  cityRoot = "${stateRoot}/city";
  rigRoot = "${stateRoot}/rigs/d2b";
  gcHome = "${stateRoot}/gc";
  homeRoot = "${stateRoot}/home";
  configRoot = "${stateRoot}/config";
  xdgStateRoot = "${stateRoot}/state";
  cacheRoot = "${stateRoot}/cache";
  runtimeRoot = "/run/d2b-gascity";
  supervisorPort = 8372;
  apiProxyPort = 18372;
  effectivePackage = if cfg.package == null then pkgs.hello else cfg.package;
  packagePath = toString effectivePackage;

  quoteToml = value:
    "\""
    + lib.replaceStrings [ "\\" "\"" ] [ "\\\\" "\\\"" ] value
    + "\"";

  supervisorHost =
    if cfg.dashboard.remote.hostname == null then
      ""
    else
      "\nallowed_hosts = [${quoteToml cfg.dashboard.remote.hostname}]";

  supervisorConfigText = ''
    [supervisor]
    bind = "127.0.0.1"
    port = ${toString supervisorPort}${supervisorHost}
  '';

  credentials = lib.concatLists [
    (lib.optional (cfg.credentials.copilotTokenFile != null)
      "copilot-token:${cfg.credentials.copilotTokenFile}")
    (lib.optional (cfg.credentials.githubPublicationTokenFile != null)
      "github-publication-token:${cfg.credentials.githubPublicationTokenFile}")
    (lib.optional (cfg.credentials.githubPublicationPolicyFile != null)
      "github-publication-policy:${cfg.credentials.githubPublicationPolicyFile}")
    (lib.optional (cfg.credentials.githubPublicationAppKeyFile != null)
      "github-publication-app-key:${cfg.credentials.githubPublicationAppKeyFile}")
    (lib.optional (cfg.credentials.githubPublicationAppConfigFile != null)
      "github-publication-app-config:${cfg.credentials.githubPublicationAppConfigFile}")
    (lib.optional (cfg.credentials.discordBotTokenFile != null)
      "discord-bot-token:${cfg.credentials.discordBotTokenFile}")
  ];

  stateDirectories = [
    "d /var/lib/d2b-gascity 0750 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/city 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/rigs 0750 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/rigs/d2b 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/gc 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/home 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/config 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/state 0700 d2b-gascity d2b-gascity -"
    "d /var/lib/d2b-gascity/cache 0700 d2b-gascity d2b-gascity -"
  ];

  trustedProxyPartitions = lib.partition (lib.hasInfix ":")
    cfg.dashboard.remote.trustedExternalProxyCidrs;
  trustedIPv4 = trustedProxyPartitions.wrong;
  trustedIPv6 = trustedProxyPartitions.right;
  nftSet = values:
    if values == [ ] then
      "0.0.0.0/32"
    else
      lib.concatStringsSep ", " values;
  nftSet6 = values:
    if values == [ ] then
      "::/128"
    else
      lib.concatStringsSep ", " values;
  remoteInputRules = lib.optionalString cfg.dashboard.remote.enable ''
    iifname "${cfg.dashboard.remote.relayInterface}" tcp dport ${toString cfg.dashboard.remote.relayPort} ip saddr != { ${nftSet trustedIPv4} } drop
    iifname "${cfg.dashboard.remote.relayInterface}" tcp dport ${toString cfg.dashboard.remote.relayPort} ip6 saddr != { ${nftSet6 trustedIPv6} } drop
    iifname "${cfg.dashboard.remote.relayInterface}" tcp dport ${toString cfg.dashboard.remote.authPort} ip saddr != { ${nftSet trustedIPv4} } drop
    iifname "${cfg.dashboard.remote.relayInterface}" tcp dport ${toString cfg.dashboard.remote.authPort} ip6 saddr != { ${nftSet6 trustedIPv6} } drop
  '';
  remoteOutputRules = lib.optionalString cfg.dashboard.remote.enable ''
    oifname "lo" tcp dport ${toString cfg.dashboard.remote.tinyauthPort} meta skuid != 41081 drop
  '';
  nftRules = ''
    table inet d2b_gascity {
      chain input {
        type filter hook input priority 0; policy accept;
${remoteInputRules}
      }

      chain output {
        type filter hook output priority 0; policy accept;
        oifname "lo" tcp dport ${toString supervisorPort} meta skuid != { 41080${lib.optionalString cfg.dashboard.remote.enable ", 41081"} } drop
        oifname "lo" tcp dport ${toString apiProxyPort} meta skuid != 41080 drop
${remoteOutputRules}
${lib.optionalString (cfg.dolt.fixedPort != null)
  ''        oifname "lo" tcp dport ${toString cfg.dolt.fixedPort} meta skuid != 41080 drop
''}
      }
    }
  '';
  nftBinary = "${pkgs.nftables}/bin/nft";
  nftFirewallCommands = ''
    ${nftBinary} -f - <<'EOF'
destroy table inet d2b_gascity
${nftRules}
EOF
  '';
in
{
  imports = [
    ./options.nix
    ./ingress-relay.nix
  ];

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = config.networking.firewall.enable;
        message = "services.d2bGasCity requires networking.firewall.enable = true.";
      }
      {
        assertion = config.networking.firewall.backend == "iptables";
        message = "services.d2bGasCity requires networking.firewall.backend = \"iptables\".";
      }
    ];

    users.groups.d2b-gascity = { };
    users.groups.d2b-gascity-operators = {
      members = cfg.operators.users;
    };
    users.users.d2b-gascity = {
      uid = 41080;
      isSystemUser = true;
      group = "d2b-gascity";
      home = stateRoot;
      createHome = false;
      linger = true;
      shell = pkgs.bash;
      description = "Dedicated Gas City supervisor";
    };

    environment.systemPackages = [ effectivePackage ];
    environment.etc."d2b-gascity/supervisor.toml" = {
      text = supervisorConfigText;
      mode = "0444";
    };

    systemd.tmpfiles.rules = stateDirectories;
    networking.firewall.interfaces.${cfg.dashboard.remote.relayInterface}.allowedTCPPorts =
      lib.mkIf cfg.dashboard.remote.enable (lib.mkAfter [
        cfg.dashboard.remote.relayPort
        cfg.dashboard.remote.authPort
      ]);
    # Keep the stale table on stop: listeners disappear, so it is harmless and
    # avoiding removal prevents a reload gap or foreign mutation.
    networking.firewall.extraCommands = lib.mkAfter nftFirewallCommands;

    systemd.services.d2b-gascity = {
      description = "Standalone Gas City supervisor";
      wantedBy = [ "multi-user.target" ];
      unitConfig = {
        StartLimitIntervalSec = 60;
        StartLimitBurst = 5;
      };
      serviceConfig = {
        Type = "exec";
        User = "d2b-gascity";
        Group = "d2b-gascity";
        WorkingDirectory = stateRoot;
        StateDirectory = "d2b-gascity";
        StateDirectoryMode = "0750";
        RuntimeDirectory = "d2b-gascity";
        RuntimeDirectoryMode = "0750";

        ExecStart = pkgs.writeShellScript "d2b-gascity-supervisor" ''
          set -eu
          if [ -n "''${CREDENTIALS_DIRECTORY:-}" ] && [ -f "$CREDENTIALS_DIRECTORY/copilot-token" ]; then
            COPILOT_GITHUB_TOKEN=$(${pkgs.coreutils}/bin/tr -d '\n' < "$CREDENTIALS_DIRECTORY/copilot-token")
            export COPILOT_GITHUB_TOKEN
          fi
          exec ${packagePath}/bin/gc supervisor run
        '';
        Restart = "on-failure";
        RestartSec = "5s";
        TimeoutStartSec = "5min";
        TimeoutStopSec = "2min";
        KillMode = "control-group";

        CPUQuota = cfg.resources.cpuQuota;
        MemoryHigh = cfg.resources.memoryHigh;
        MemoryMax = cfg.resources.memoryMax;
        MemorySwapMax = cfg.resources.memorySwapMax;
        TasksMax = cfg.resources.tasksMax;

        AmbientCapabilities = [ "" ];
        CapabilityBoundingSet = [ "" ];
        NoNewPrivileges = true;
        PrivateTmp = false;
        PrivateDevices = false;
        ProtectHome = true;
        ProtectSystem = "strict";
        ProtectKernelTunables = true;
        ProtectKernelModules = true;
        ProtectKernelLogs = true;
        ProtectKernelKeyring = true;
        ProtectControlGroups = true;
        ProtectClock = true;
        ProtectHostname = true;
        RestrictSUIDSGID = true;
        LockPersonality = true;
        UMask = "0077";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];

        ReadWritePaths = [
          stateRoot
          runtimeRoot
          "/tmp"
        ];
        ReadOnlyPaths = [
          "${packagePath}/share/d2b-gascity"
        ];
        BindReadOnlyPaths = [
          "/etc/d2b-gascity/supervisor.toml:${gcHome}/supervisor.toml"
        ];

        Environment = [
          "HOME=${homeRoot}"
          "XDG_CONFIG_HOME=${configRoot}"
          "XDG_STATE_HOME=${xdgStateRoot}"
          "XDG_CACHE_HOME=${cacheRoot}"
          "XDG_RUNTIME_DIR=${runtimeRoot}"
          "GC_HOME=${gcHome}"
          "DOLT_ROOT_PATH=${gcHome}/dolt"
          "GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service"
          "GC_SUPERVISOR_SYSTEMD_SCOPE=system"
          "TMPDIR=/tmp"
          "GIT_CONFIG_NOSYSTEM=1"
          "GIT_CONFIG_GLOBAL=${gcHome}/gitconfig"
          "COPILOT_ALLOW_ALL=true"
          "PATH=${packagePath}/bin:${pkgs.openssl}/bin:/run/current-system/sw/bin"
        ] ++ lib.optional (cfg.dolt.fixedPort != null)
          "GC_DOLT_PORT=${toString cfg.dolt.fixedPort}";

        LoadCredential = credentials;
      };
    };

    systemd.sockets.d2b-gascity-api-proxy = {
      description = "Gas City standalone API compatibility proxy socket";
      wantedBy = [ "sockets.target" ];
      listenStreams = [ "127.0.0.1:${toString apiProxyPort}" ];
    };

    systemd.services.d2b-gascity-api-proxy = {
      description = "Gas City standalone API compatibility proxy";
      after = [ "d2b-gascity-api-proxy.socket" ];
      serviceConfig = {
        Type = "exec";
        User = "d2b-gascity";
        Group = "d2b-gascity";
        ExecStart =
          "${pkgs.systemd}/lib/systemd/systemd-socket-proxyd 127.0.0.1:${toString supervisorPort}";
        Restart = "on-failure";
        RestartSec = "5s";
        TimeoutStartSec = "30s";
        TimeoutStopSec = "30s";
        KillMode = "control-group";
        LimitNOFILE = 4096;

        AmbientCapabilities = [ "" ];
        CapabilityBoundingSet = [ "" ];
        NoNewPrivileges = true;
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
        RestrictSUIDSGID = true;
        LockPersonality = true;
        UMask = "0077";
        RestrictAddressFamilies = [ "AF_UNIX" "AF_INET" "AF_INET6" ];
      };
    };
  };
}
