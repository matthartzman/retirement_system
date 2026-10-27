"""snapshot_prices_between(): the latest stored price per symbol inside a UTC window (Live Snapshot closes)."""
import sqlite3

from src.portfolio_analytics import snapshot_prices, snapshot_prices_between


def _backdate(db, symbol, price, as_of):
    with sqlite3.connect(db) as con:
        con.execute("UPDATE price_snapshots SET as_of=? WHERE symbol=? AND price=?", (as_of, symbol, price))
    con.close()


def test_latest_inside_window_per_symbol(tmp_path):
    db = tmp_path / "retirement_system_v10.db"
    rows = [("ITOT", 139.0, "2025-12-31 18:00:00"),   # during the session: too early
            ("ITOT", 140.0, "2025-12-31 22:00:00"),
            ("ITOT", 141.0, "2026-01-02 03:00:00"),   # latest inside: wins
            ("ITOT", 145.0, "2026-01-02 15:00:00"),   # after the next open: too late
            ("IXUS", 61.0, "2026-01-01 12:00:00")]
    for sym, px, as_of in rows:
        snapshot_prices({sym: px}, db_path=db)
        _backdate(db, sym, px, as_of)
    out = snapshot_prices_between(["itot", "IXUS", "AVUV"], "2025-12-31 21:00:00", "2026-01-02 14:30:00", db_path=db)
    assert out == {"ITOT": 141.0, "IXUS": 61.0}


def test_no_database_or_no_symbols(tmp_path):
    assert snapshot_prices_between(["ITOT"], "2025-12-31 21:00:00", "2026-01-02 14:30:00", db_path=tmp_path / "none.db") == {}
    assert snapshot_prices_between([], "a", "b", db_path=tmp_path / "none.db") == {}
