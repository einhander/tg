from __future__ import annotations

import csv
import io
import json
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse, Response

from tgapp.application.ports import SessionArchiveService, SessionRepository
from tgapp.application.use_cases import export_session
from tgapp.application.error_responses import archive_corrupted, UserError
from tgapp.web.deps import get_config, get_or_create_session_state, get_processing_state, get_storage, get_kinetics_repo

router = APIRouter(prefix="/export")


def _archive_service() -> SessionArchiveService:
    """Lazy adapter for SessionArchiveService."""
    from tgapp.infrastructure.serialization import pack_session_directory
    class _Adapter:
        def pack_session_directory(self, source: Path, dest: Path) -> Path:
            return pack_session_directory(source, dest)
        def unpack_session_archive(self, archive_path: Path, dest_dir: Path) -> None:
            from tgapp.infrastructure.serialization import unpack_session_archive
            unpack_session_archive(archive_path, dest_dir)
    return _Adapter()


@router.get("/session", name="export_session")
def export_session_route(request: Request, response: Response):
    """Export session as ZIP archive (PLAN_AUDIT §16.3).

    - Creates archive in a temp directory (never inside session dir)
    - Uses atomic temp file → serve → cleanup pattern
    """
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    try:
        state = export_session(storage, _archive_service(), session_state)
    except Exception:
        # Return a minimal error response without exposing internals
        from tgapp.application.view_models import page_context
        from tgapp.web.deps import get_templates, ensure_session_cookie
        err = archive_corrupted("session archive")
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings={},
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
        return ensure_session_cookie(request, template_response, session_state)
    sid = session_state.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise HTTPException(status_code=404, detail="Session archive is unavailable")

    session_dir = storage.session_dir(sid)
    archive_name = f"{sid}.tg"

    # PLAN_AUDIT §16.3: create archive outside session directory
    tmpdir = tempfile.mkdtemp()
    try:
        tmp_archive = Path(tmpdir) / archive_name
        _archive_service().pack_session_directory(session_dir, tmp_archive)
        archive_bytes = tmp_archive.read_bytes()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return Response(
        content=archive_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={archive_name}"},
    )


@router.get("/plot", name="export_plot")
def export_plot():
    return PlainTextResponse("Plot export is not implemented yet.", status_code=501)


# ---------------------------------------------------------------------------
# Kinetics export endpoints
# ---------------------------------------------------------------------------

@router.get("/kinetics/studies/{study_id}/analyses/{analysis_id}/csv", name="export_kinetics_csv")
def export_kinetics_csv(request: Request, study_id: str, analysis_id: str):
    """Export kinetics analysis result as CSV."""
    repo = get_kinetics_repo(request)
    try:
        result_data = repo.load_analysis(study_id, analysis_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "alpha",
        "activation_energy_kj_mol",
        "method_id",
        "method_version",
        "slope",
        "intercept",
        "r_squared",
        "slope_standard_error",
        "run_count",
        "status",
        "warnings",
    ])

    for p in result_data.get("points", []):
        e_kj = p["activation_energy_j_mol"] / 1000 if p["activation_energy_j_mol"] is not None else ""
        writer.writerow([
            p["alpha"],
            e_kj,
            result_data.get("method_id", ""),
            result_data.get("method_version", ""),
            p["slope"],
            p["intercept"],
            p["r_squared"],
            p["slope_standard_error"],
            len(p.get("run_ids", [])),
            p["status"],
            "; ".join(p.get("warnings", [])) if p.get("warnings") else "",
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=kinetics_{analysis_id}.csv"},
    )


@router.get("/kinetics/studies/{study_id}/analyses/{analysis_id}/json", name="export_kinetics_json")
def export_kinetics_json(request: Request, study_id: str, analysis_id: str):
    """Export full kinetics analysis result as JSON."""
    repo = get_kinetics_repo(request)
    try:
        result_data = repo.load_analysis(study_id, analysis_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    return Response(
        content=json.dumps(result_data, indent=2, ensure_ascii=False),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=kinetics_{analysis_id}.json"},
    )