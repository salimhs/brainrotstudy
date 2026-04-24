from brainrotstudy import db
from brainrotstudy.schemas import JobOptions, JobStage, JobStatus, Vibe


def test_crud_roundtrip() -> None:
    job = db.create_job(
        "abc12345",
        title="Mitosis",
        input_kind="topic",
        input_filename=None,
        options=JobOptions(vibe=Vibe.PROFESSOR),
    )
    assert job.id == "abc12345"
    assert job.status == JobStatus.QUEUED
    assert job.options.vibe == Vibe.PROFESSOR

    updated = db.update_job("abc12345", status=JobStatus.RUNNING, stage=JobStage.SCRIPT, progress=30)
    assert updated is not None
    assert updated.status == JobStatus.RUNNING
    assert updated.stage == JobStage.SCRIPT
    assert updated.progress == 30

    listed = db.list_jobs()
    assert len(listed) == 1
    assert listed[0].id == "abc12345"

    assert db.delete_job("abc12345") is True
    assert db.get_job("abc12345") is None
