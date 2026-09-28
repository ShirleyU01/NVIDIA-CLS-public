from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Optional

from backend.config import settings
from backend.database import SessionLocal
from backend.models import EvidencePacket, Rubric, Session as DbSession
from integration.build_session_from_oral_exam import build_session_from_oral_exam
from integration.evidence_packet import llm as default_llm
from integration.evidence_packet.pipeline import run_evidence_packet


def run_evidence_job(session_id: str, *, rubric_id: Optional[int] = None) -> None:
    """
    Synchronous evidence-packet job (can be wrapped in a FastAPI BackgroundTask).

    - Reads session artifacts from the configured JETSON_SESSIONS_ROOT.
    - Builds normalized session JSON.
    - Runs evidence packet pipeline.
    - Persists packet JSON into the database and updates session scores.
    """
    db = SessionLocal()
    db_session: Optional[DbSession] = None
    try:
        db_session = db.get(DbSession, session_id)
        if not db_session:
            return

        artifacts = dict(db_session.artifacts or {})
        artifacts["evidence_job"] = {
            "status": "processing",
            "started_at": datetime.utcnow().isoformat(),
        }
        db_session.artifacts = artifacts
        db_session.evidence_packet_status = "processing"
        db.commit()

        if rubric_id is None:
            rubric_id = (
                db_session.assessment_id and db_session.assessment.rubric_id
            )  # type: ignore[union-attr]
        rubric: Optional[Rubric] = db.get(Rubric, rubric_id) if rubric_id is not None else None
        if not rubric:
            return

        session_dir = settings.JETSON_SESSIONS_ROOT / session_id
        if not session_dir.exists():
            return

        settings.EVIDENCE_PACKET_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
        normalized_session = build_session_from_oral_exam(session_dir)

        session_json_path = (
            settings.EVIDENCE_PACKET_STORAGE_ROOT / f"{session_id}.session.json"
        )
        session_json_path.write_text(
            json.dumps(normalized_session, indent=2), encoding="utf-8"
        )

        rubric_path = settings.EVIDENCE_PACKET_STORAGE_ROOT / f"rubric_{rubric_id}.json"
        rubric_path.write_text(json.dumps(rubric.rubric_json, indent=2), encoding="utf-8")

        out_path = settings.EVIDENCE_PACKET_STORAGE_ROOT / f"evidence_packet_{session_id}.json"

        # Choose LLM backend:
        # - If OPENAI_API_KEY is set and openai backend is available, use it.
        # - Otherwise, fall back to the default stub, which will raise a
        #   clear NotImplementedError that we capture and surface in artifacts.
        llm_fn = default_llm.llm_complete
        if os.environ.get("OPENAI_API_KEY"):
            try:
                from integration.evidence_packet.llm_openai import (  # type: ignore[import]
                    llm_complete as openai_llm_complete,
                )

                llm_fn = openai_llm_complete
            except Exception:
                # Keep default_llm; the job will record a failure explaining why.
                pass

        packet = run_evidence_packet(
            str(rubric_path),
            str(session_json_path),
            str(out_path),
            llm_complete_fn=llm_fn,
        )

        packet_rec = (
            db.query(EvidencePacket)
            .filter(EvidencePacket.session_id == session_id)
            .one_or_none()
        )
        if packet_rec is None:
            packet_rec = EvidencePacket(
                session_id=session_id, rubric_id=rubric.id, packet_json=packet
            )
            db.add(packet_rec)
        else:
            packet_rec.packet_json = packet

        artifacts = dict(db_session.artifacts or {})
        evidence_job = dict(artifacts.get("evidence_job") or {})
        evidence_job.update(
            {
                "status": "ready",
                "finished_at": datetime.utcnow().isoformat(),
                "packet_path": str(out_path),
            }
        )
        artifacts["evidence_job"] = evidence_job
        db_session.artifacts = artifacts
        db_session.evidence_packet_status = "ready"
        db_session.score_total = packet.get("total_score")
        db_session.score_max = packet.get("max_score")
        db_session.status = "evidence_ready"
        db.commit()
    except Exception as e:
        if db_session is not None:
            artifacts = dict(db_session.artifacts or {})
            evidence_job = dict(artifacts.get("evidence_job") or {})
            evidence_job.update(
                {
                    "status": "failed",
                    "finished_at": datetime.utcnow().isoformat(),
                    "error": str(e),
                }
            )
            artifacts["evidence_job"] = evidence_job
            db_session.artifacts = artifacts
            db_session.evidence_packet_status = "failed"
            db_session.status = "evidence_failed"
            db.commit()
        print(f"[evidence_jobs] Failed for session {session_id}: {e}")
    finally:
        db.close()

