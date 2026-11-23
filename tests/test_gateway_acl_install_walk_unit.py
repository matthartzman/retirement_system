"""X-2: `acl check` walks the install tree and also covers gateway.json and the log folder (Windows APIs faked)."""
from __future__ import annotations

import pytest

from src.gateway import acl

pytestmark = pytest.mark.unit
ME = "S-1-5-21-1-2-3-1001"
WORKER = "S-1-5-21-1-2-3-2001"
FULL = 0x1F01FF
READ = 0x1200A9


def _dacl(*pairs, protected=True):
    return acl.Dacl(protected, tuple(acl.Ace(sid, True, mask, False) for sid, mask in pairs), owner=acl.ADMINISTRATORS)


GOOD = _dacl((acl.SYSTEM, FULL), (acl.ADMINISTRATORS, FULL), (ME, FULL), (acl.USERS, READ))


@pytest.fixture
def tree(tmp_path, monkeypatch):
    install = tmp_path / "app"
    (install / "runtime" / "lib").mkdir(parents=True)
    (install / "runtime" / "lib" / "good.py").write_text("x")
    (install / "runtime" / "lib" / "swap.pyd").write_text("x")
    cfg_dir = tmp_path / "cfg"
    cfg_dir.mkdir()
    (cfg_dir / "gateway.json").write_text("{}")
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "gateway.log").write_text("")
    table: dict = {}
    monkeypatch.setattr(acl, "read_dacl", lambda p: table.get(p, GOOD))
    return install, cfg_dir / "gateway.json", logs, table


def _data_root(tmp_path):
    root = tmp_path / "data"
    (root / "users").mkdir(parents=True)
    return root


def test_a_clean_layout_reports_nothing(tree, tmp_path, monkeypatch):
    install, cfg, logs, table = tree
    private = _dacl((acl.SYSTEM, FULL), (acl.ADMINISTRATORS, FULL), (ME, FULL))
    root = _data_root(tmp_path)
    table.update({root: private, root / "users": private})
    findings = acl.check_layout(data_root=root, gateway_sid=ME, workers={1: ("rpw_1", WORKER)}, install_dir=install,
                                config_file=cfg, log_dir=logs)
    assert [f for f in findings if "data" not in f.split(":")[0]] == []


def test_a_worker_writable_file_deep_in_the_install_is_found(tree, tmp_path):
    install, cfg, logs, table = tree
    table[install / "runtime" / "lib" / "swap.pyd"] = _dacl((acl.SYSTEM, FULL), (WORKER, FULL))
    findings = acl.check_readonly(install, writers={acl.SYSTEM, acl.ADMINISTRATORS, ME}, workers={WORKER: "worker account rpw_1"},
                                  what="install folder", walk=True)
    assert findings == ["install folder [runtime/lib/swap.pyd]: worker account rpw_1 can write"]
    # without the walk the old top-level-only check misses it (the gap X-2 describes)
    assert acl.check_readonly(install, writers={acl.SYSTEM, acl.ADMINISTRATORS, ME}, workers={}, what="install folder") == []


def test_a_broad_group_that_can_write_a_child_folder_is_found(tree):
    install, cfg, logs, table = tree
    table[install / "runtime"] = _dacl((acl.SYSTEM, FULL), (acl.USERS, FULL))
    findings = acl.check_readonly(install, writers={acl.SYSTEM, acl.ADMINISTRATORS, ME}, workers={}, what="install folder", walk=True)
    assert findings == ["install folder [runtime]: Users can write"]


def test_the_walk_cap_is_reported_not_silently_ignored(tree):
    install, cfg, logs, table = tree
    findings = acl.check_readonly(install, writers={acl.SYSTEM, acl.ADMINISTRATORS, ME}, workers={}, what="install folder", walk=True, max_walk=2)
    assert findings and "more than 2 entries" in findings[-1]


def test_config_file_its_folder_and_the_log_folder_are_checked(tree, tmp_path):
    install, cfg, logs, table = tree
    table[cfg] = _dacl((acl.SYSTEM, FULL), (WORKER, FULL))
    table[cfg.parent] = _dacl((acl.SYSTEM, FULL), (acl.USERS, FULL))
    table[logs / "gateway.log"] = _dacl((acl.SYSTEM, FULL), (WORKER, FULL))
    root = _data_root(tmp_path)
    findings = acl.check_layout(data_root=root, gateway_sid=ME, workers={1: ("rpw_1", WORKER)}, config_file=cfg, log_dir=logs)
    assert "gateway.json: worker account rpw_1 can write" in findings
    assert "gateway.json folder: Users can write" in findings
    assert "log folder [gateway.log]: worker account rpw_1 can write" in findings


def test_a_missing_config_or_log_folder_is_a_finding(tree, tmp_path):
    install, cfg, logs, table = tree
    root = _data_root(tmp_path)
    findings = acl.check_layout(data_root=root, gateway_sid=ME, workers={}, config_file=tmp_path / "nope.json", log_dir=tmp_path / "nologs")
    assert any(f.startswith("gateway.json: missing") for f in findings) and any(f.startswith("log folder: missing") for f in findings)
