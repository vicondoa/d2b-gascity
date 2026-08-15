{ pkgs
, module
, gasCityContributor
}:

pkgs.testers.runNixOSTest {
  name = "d2b-gascity";

  nodes.machine = { ... }: {
    imports = [ module ];

    services.d2bGasCity = {
      enable = true;
      package = gasCityContributor;
    };

    environment.systemPackages = [
      pkgs.curl
      pkgs.coreutils
      pkgs.git
      pkgs.jq
      pkgs.lsof
      pkgs.procps
      pkgs.tmux
    ];

    virtualisation.memorySize = 4096;
    virtualisation.cores = 2;
    system.stateVersion = "25.11";
  };

  testScript = ''
    start_all()
    machine.wait_for_unit("d2b-gascity.service")

    machine.succeed(
        "test \"$(systemctl show -P User d2b-gascity.service)\" = d2b-gascity"
    )
    machine.succeed(
        "test \"$(systemctl show -P KillMode d2b-gascity.service)\" = control-group"
    )
    machine.succeed(
        "test \"$(systemctl show -P Restart d2b-gascity.service)\" = on-failure"
    )
    machine.succeed(
        "test -d /var/lib/d2b-gascity/city && "
        "test -d /var/lib/d2b-gascity/rigs/d2b && "
        "test -d /var/lib/d2b-gascity/gc"
    )
    machine.succeed(
        "test \"$(systemctl list-unit-files 'd2b-gascity*' --no-legend | "
        "awk '{print $1}' | wc -l)\" = 1"
    )

    supervisor_env = (
        "HOME=/var/lib/d2b-gascity/home "
        "XDG_CONFIG_HOME=/var/lib/d2b-gascity/config "
        "XDG_STATE_HOME=/var/lib/d2b-gascity/state "
        "XDG_CACHE_HOME=/var/lib/d2b-gascity/cache "
        "XDG_RUNTIME_DIR=/run/d2b-gascity "
        "GC_HOME=/var/lib/d2b-gascity/gc "
        "GC_SUPERVISOR_SYSTEMD_UNIT=d2b-gascity.service "
        "GC_SUPERVISOR_SYSTEMD_SCOPE=system "
        "DOLT_ROOT_PATH=/var/lib/d2b-gascity/dolt-root "
        "GIT_CONFIG_NOSYSTEM=1 "
        "GIT_CONFIG_GLOBAL=/var/lib/d2b-gascity/gitconfig "
    )
    as_city = "runuser -u d2b-gascity -- env " + supervisor_env

    machine.wait_until_succeeds(
        as_city + "curl --fail --silent "
        "http://127.0.0.1:8372/health",
        timeout=60,
    )
    machine.succeed(
        "test \"$(pgrep -u d2b-gascity -f 'gc supervisor run' | wc -l)\" = 1"
    )

    machine.succeed(
        as_city
        + "${gasCityContributor}/bin/dolt config --global --add "
        "user.name fixture"
    )
    machine.succeed(
        as_city
        + "${gasCityContributor}/bin/dolt config --global --add "
        "user.email fixture@example.test"
    )
    machine.succeed(
        as_city
        + "${gasCityContributor}/bin/gc init --template empty --no-start "
        "--skip-provider-readiness --yes /var/lib/d2b-gascity/city"
    )
    machine.succeed(
        as_city
        + "${gasCityContributor}/bin/gc start "
        "/var/lib/d2b-gascity/city --json"
    )
    machine.wait_until_succeeds(
        "pgrep -u d2b-gascity -f 'dolt.*sql-server' >/dev/null",
        timeout=90,
    )
    machine.wait_until_succeeds(
        as_city + "curl --fail --silent "
        "http://127.0.0.1:8372/health",
        timeout=60,
    )
    city_hash = machine.succeed(
        "sha256sum /var/lib/d2b-gascity/city/city.toml"
    ).strip()

    machine.succeed("systemctl stop d2b-gascity.service")
    machine.fail("pgrep -u d2b-gascity -f 'gc supervisor run'")
    machine.fail("pgrep -u d2b-gascity -f 'dolt.*sql-server'")

    machine.succeed("systemctl start d2b-gascity.service")
    machine.wait_for_unit("d2b-gascity.service")
    machine.wait_until_succeeds(
        as_city + "curl --fail --silent "
        "http://127.0.0.1:8372/health",
        timeout=60,
    )
    machine.succeed(
        "test \"$(pgrep -u d2b-gascity -f 'gc supervisor run' | wc -l)\" = 1"
    )
    machine.succeed(
        "test \"$(sha256sum /var/lib/d2b-gascity/city/city.toml)\" = "
        + repr(city_hash)
    )
    machine.wait_until_succeeds(
        "pgrep -u d2b-gascity -f 'dolt.*sql-server' >/dev/null",
        timeout=90,
    )
  '';
}
