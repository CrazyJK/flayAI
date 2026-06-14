"""stabilizer 잡 모델 + 설정 단위 테스트 (ffmpeg 불필요)."""

from __future__ import annotations

from packages.stabilizer import job as J
from packages.stabilizer.config import stabilize_config


def test_config_defaults():
    c = stabilize_config()
    p = c["smoothing_presets"]
    assert p["lock"] > p["smooth"] > p["dejitter"]  # 강도 순서
    assert c["default_mode"] in ("background", "person")
    assert c["concurrency"] >= 1


def test_job_status_roundtrip(tmp_path, monkeypatch):
    # work_dir 를 tmp 로 격리(실제 data/stabilize 오염 방지)
    monkeypatch.setattr(J, "_work_root", lambda: tmp_path)

    job_id = J.new_job("background", "smooth", {"foo": "bar"})
    st = J.get_status(job_id)
    assert st is not None
    assert st["status"] == "queued"
    assert st["mode"] == "background"
    assert st["options"] == {"foo": "bar"}

    J.set_status(job_id, status="running", progress=50, stage="detect")
    st2 = J.get_status(job_id)
    assert st2["progress"] == 50
    assert st2["stage"] == "detect"
    assert st2["updated_at"] >= st["created_at"]

    jobs = J.list_jobs()
    assert any(j["job_id"] == job_id for j in jobs)


def test_get_status_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(J, "_work_root", lambda: tmp_path)
    assert J.get_status("nope") is None
