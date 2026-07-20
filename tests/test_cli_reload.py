from __future__ import annotations

from vaultgfs import cli_reload


def test_desired_units_includes_prune_timer_with_default_schedule():
    units = cli_reload.desired_units({"jobs": []})

    prune_timer = cli_reload.SYSTEMD_DIR / "vaultgfs-prune.timer"
    prune_service = cli_reload.SYSTEMD_DIR / "vaultgfs-prune.service"

    assert prune_service in units
    assert prune_timer in units
    assert "ExecStart=/usr/local/bin/vaultgfs-prune --apply" in units[prune_service]
    assert "OnCalendar=Sun *-*-* 20:0:00" in units[prune_timer]


def test_desired_units_includes_pfsense_timer():
    units = cli_reload.desired_units(
        {
            "jobs": [
                {
                    "name": "pfsense-main",
                    "enabled": True,
                    "type": "pfsense-config",
                    "schedule": "0 4 * * *",
                }
            ]
        }
    )

    service = cli_reload.SYSTEMD_DIR / "vaultgfs-pfsense-main-dump.service"
    timer = cli_reload.SYSTEMD_DIR / "vaultgfs-pfsense-main-dump.timer"

    assert service in units
    assert timer in units
    assert "ExecStart=/usr/local/bin/vaultgfs-backup --job pfsense-main" in units[service]
