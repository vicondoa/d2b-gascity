{ config, lib, ... }:

let
  inherit (lib) mkIf mkOption types;
  cfg = config.services.d2bGasCity;

  port = types.ints.between 1024 65535;
  userName = types.strMatching "^[a-z_][a-z0-9_.-]{0,31}$";
  path = types.nullOr types.str;
  hostname = types.nullOr (types.strMatching "^[A-Za-z0-9][A-Za-z0-9.-]{0,252}$");
  cidr = types.strMatching "^[0-9A-Fa-f:.]+/[0-9]{1,3}$";

  absolutePath = value:
    lib.hasPrefix "/" value
    && value != "/"
    && !(lib.hasInfix "//" value)
    && !(lib.hasInfix ".." value)
    && value != "/nix/store"
    && !(lib.hasPrefix "/nix/store/" value)
    && !(lib.hasInfix "\n" value)
    && !(lib.hasInfix "\r" value);

  validHostname = value:
    value != null
    && !(lib.hasInfix ".." value)
    && !(lib.hasPrefix "." value)
    && !(lib.hasSuffix "." value);

  validListenAddress = value:
    builtins.match "^[0-9A-Fa-f:.]+$" value != null
    && value != "0.0.0.0"
    && value != "::";

  validInterface = value:
    builtins.match "^[A-Za-z0-9_.:-]+$" value != null;

  packagePassthru =
    if cfg.package == null then
      { }
    else
      (cfg.package.passthru or { });

  resolvedPackage = override: name:
    if override != null then
      override
    else if builtins.hasAttr name packagePassthru then
      builtins.getAttr name packagePassthru
    else
      null;

  resolvedTinyAuth = resolvedPackage cfg.dashboard.remote.tinyauthPackage "tinyauth";
  resolvedNginx = resolvedPackage cfg.dashboard.remote.nginxPackage "nginx";
  dashboardHostnameLabels =
    if cfg.dashboard.remote.hostname == null then
      [ ]
    else
      lib.splitString "." cfg.dashboard.remote.hostname;
  authHostnameLabels =
    if cfg.dashboard.remote.authHostname == null then
      [ ]
    else
      lib.splitString "." cfg.dashboard.remote.authHostname;

  configuredPorts =
    [ 8372 ]
    ++ lib.optionals cfg.dashboard.remote.enable [
      cfg.dashboard.remote.relayPort
      cfg.dashboard.remote.authPort
      cfg.dashboard.remote.tinyauthPort
    ]
    ++ lib.optional (cfg.dolt.fixedPort != null) cfg.dolt.fixedPort;

  pathAssertions = lib.concatLists [
    [
      {
        assertion = absolutePath cfg.copilot.providerSelectionFile;
        message = "services.d2bGasCity.copilot.providerSelectionFile must be absolute.";
      }
    ]
    (lib.optional (cfg.credentials.copilotTokenFile != null) {
      assertion = absolutePath cfg.credentials.copilotTokenFile;
      message = "services.d2bGasCity.credentials.copilotTokenFile must be absolute.";
    })
    (lib.optional (cfg.credentials.githubPublicationTokenFile != null) {
      assertion = absolutePath cfg.credentials.githubPublicationTokenFile;
      message = "services.d2bGasCity.credentials.githubPublicationTokenFile must be absolute.";
    })
    (lib.optional (cfg.credentials.githubPublicationPolicyFile != null) {
      assertion = absolutePath cfg.credentials.githubPublicationPolicyFile;
      message = "services.d2bGasCity.credentials.githubPublicationPolicyFile must be absolute.";
    })
    (lib.optional (cfg.credentials.discordBotTokenFile != null) {
      assertion = absolutePath cfg.credentials.discordBotTokenFile;
      message = "services.d2bGasCity.credentials.discordBotTokenFile must be absolute.";
    })
    (lib.optional (
      cfg.dashboard.remote.tinyauthUsersFile != null
    ) {
      assertion = absolutePath cfg.dashboard.remote.tinyauthUsersFile;
      message = "services.d2bGasCity.dashboard.remote.tinyauthUsersFile must be absolute.";
    })
  ];
in
{
  options.services.d2bGasCity = {
    enable = mkOption {
      type = types.bool;
      default = false;
      description = "Run the standalone Gas City supervisor.";
    };

    package = mkOption {
      type = types.nullOr types.package;
      default = null;
      description = "Gas City contributor package containing gc and portable assets.";
    };

    copilot.providerSelectionFile = mkOption {
      type = types.str;
      default = "/var/lib/d2b-gascity/config/provider-selection.json";
      description = "Machine-local Copilot readiness selection written before startup.";
    };

    dolt.fixedPort = mkOption {
      type = types.nullOr port;
      default = null;
      description = "Optional fixed GC-managed Dolt port. Null selects upstream allocation.";
    };

    resources = {
      cpuQuota = mkOption {
        type = types.str;
        default = "100%";
        description = "CPU quota for the Gas City service.";
      };

      memoryHigh = mkOption {
        type = types.str;
        default = "2G";
        description = "MemoryHigh limit for the Gas City service.";
      };

      memoryMax = mkOption {
        type = types.str;
        default = "4G";
        description = "MemoryMax limit for the Gas City service.";
      };

      memorySwapMax = mkOption {
        type = types.str;
        default = "0";
        description = "MemorySwapMax limit for the Gas City service.";
      };

      tasksMax = mkOption {
        type = types.ints.positive;
        default = 512;
        description = "TasksMax limit for the Gas City service.";
      };
    };

    operators.users = mkOption {
      type = types.listOf userName;
      default = [ ];
      description = "Local users allowed to use the packaged operator wrappers.";
    };

    credentials = {
      copilotTokenFile = mkOption {
        type = path;
        default = null;
        description = "Optional root-owned Copilot credential source.";
      };

      githubPublicationTokenFile = mkOption {
        type = path;
        default = null;
        description = "Optional host-local GitHub publication token source.";
      };

      githubPublicationPolicyFile = mkOption {
        type = path;
        default = null;
        description = "Optional host-local GitHub publication policy source.";
      };

      discordBotTokenFile = mkOption {
        type = path;
        default = null;
        description = "Optional root-owned Discord bot-token source.";
      };
    };

    dashboard.remote = {
      enable = mkOption {
        type = types.bool;
        default = false;
        description = "Expose the embedded dashboard through TinyAuth and Nginx.";
      };

      relayAddress = mkOption {
        type = types.str;
        default = "127.0.0.1";
        description = "Address on which the authenticated relay listens.";
      };

      relayInterface = mkOption {
        type = types.str;
        default = "lo";
        description = "Interface admitted to the authenticated relay listener.";
      };

      relayPort = mkOption {
        type = port;
        default = 8373;
        description = "Authenticated dashboard relay listener port.";
      };

      authPort = mkOption {
        type = port;
        default = 8374;
        description = "Authenticated TinyAuth public listener port.";
      };

      tinyauthPort = mkOption {
        type = port;
        default = 8375;
        description = "Loopback TinyAuth port used only by the relay.";
      };

      hostname = mkOption {
        type = hostname;
        default = null;
        description = "External dashboard Host and same-origin authority.";
      };

      authHostname = mkOption {
        type = hostname;
        default = null;
        description = "External TinyAuth Host and authentication authority.";
      };

      trustedExternalProxyCidrs = mkOption {
        type = types.listOf cidr;
        default = [ ];
        description = "Source CIDRs admitted to the relay listener.";
      };

      tinyauthUsersFile = mkOption {
        type = path;
        default = null;
        description = "Root-owned TinyAuth users file loaded as a credential.";
      };

      tinyauthPackage = mkOption {
        type = types.nullOr types.package;
        default = null;
        description = "Optional TinyAuth package override.";
      };

      nginxPackage = mkOption {
        type = types.nullOr types.package;
        default = null;
        description = "Optional Nginx package override.";
      };
    };
  };

  config = mkIf cfg.enable {
    assertions =
      [
        {
          assertion = cfg.package != null;
          message = "services.d2bGasCity.package must be set when the service is enabled.";
        }
        {
          assertion = lib.unique configuredPorts == configuredPorts;
          message = "Gas City supervisor, dashboard relay, auth relay, TinyAuth, and fixed Dolt ports must be distinct.";
        }
      ]
      ++ pathAssertions
      ++ lib.optionals cfg.dashboard.remote.enable [
        {
          assertion = validHostname cfg.dashboard.remote.hostname;
          message = "dashboard.remote.hostname is required and must be a valid external Host.";
        }
        {
          assertion = validHostname cfg.dashboard.remote.authHostname;
          message = "dashboard.remote.authHostname is required and must be a valid external Host.";
        }
        {
          assertion =
            cfg.dashboard.remote.hostname != cfg.dashboard.remote.authHostname;
          message = "dashboard.remote.hostname and authHostname must be distinct.";
        }
        {
          assertion =
            cfg.dashboard.remote.hostname != null
            && cfg.dashboard.remote.authHostname != null
            && lib.hasSuffix
              ".${cfg.dashboard.remote.hostname}"
              cfg.dashboard.remote.authHostname;
          message = "dashboard.remote.authHostname must be a subdomain of dashboard.remote.hostname.";
        }
        {
          assertion =
            authHostnameLabels != [ ]
            && lib.length authHostnameLabels
              == lib.length dashboardHostnameLabels + 1
            && lib.drop 1 authHostnameLabels == dashboardHostnameLabels;
          message = "dashboard.remote.authHostname must be exactly one additional label below dashboard.remote.hostname.";
        }
        {
          assertion = cfg.dashboard.remote.trustedExternalProxyCidrs != [ ];
          message = "dashboard.remote.trustedExternalProxyCidrs is required for remote ingress.";
        }
        {
          assertion = cfg.dashboard.remote.tinyauthUsersFile != null;
          message = "dashboard.remote.tinyauthUsersFile is required for remote ingress.";
        }
        {
          assertion = validListenAddress cfg.dashboard.remote.relayAddress;
          message = "dashboard.remote.relayAddress must be a specific IPv4 or IPv6 address.";
        }
        {
          assertion = validInterface cfg.dashboard.remote.relayInterface;
          message = "dashboard.remote.relayInterface is malformed.";
        }
        {
          assertion = resolvedTinyAuth != null;
          message = "Remote ingress requires TinyAuth in package.passthru or dashboard.remote.tinyauthPackage.";
        }
        {
          assertion = resolvedNginx != null;
          message = "Remote ingress requires Nginx in package.passthru or dashboard.remote.nginxPackage.";
        }
      ];
  };
}
