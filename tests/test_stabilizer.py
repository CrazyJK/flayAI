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


def test_cleanup_old_jobs(tmp_path, monkeypatch):
    import time

    monkeypatch.setattr(J, "_work_root", lambda: tmp_path)

    def backdate(job_id, hours):
        st = J.get_status(job_id)
        st["updated_at"] = time.time() - hours * 3600
        J._write(job_id, st)

    old = J.new_job("background", "smooth")
    J.set_status(old, status="done")
    backdate(old, 100)

    recent = J.new_job("background", "smooth")
    J.set_status(recent, status="done")  # 방금 → 보존

    running = J.new_job("background", "smooth")
    J.set_status(running, status="running")
    backdate(running, 100)  # 오래됐지만 진행 중 → 보존

    removed = J.cleanup_old_jobs(retain_hours=48)
    assert removed == 1
    assert J.get_status(old) is None
    assert J.get_status(recent) is not None
    assert J.get_status(running) is not None

    # _analysis 같은 status.json 없는 디렉토리는 건드리지 않음
    (tmp_path / "_analysis").mkdir()
    assert J.cleanup_old_jobs(retain_hours=48) == 0
    assert (tmp_path / "_analysis").exists()
