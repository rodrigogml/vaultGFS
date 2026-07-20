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
