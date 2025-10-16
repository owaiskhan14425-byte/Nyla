# routers/admin_dedupe_auto.py
from fastapi import APIRouter, Query
from typing import Optional
from utils.helpers import api_response
from utils.constants import HTTP_STATUS
from services.dedupe_auto import dedupe_users_auto,cleanup_orphan_sessions_by_org
router = APIRouter()


@router.post("/admin/sessions/cleanup-orphans/by-org")
async def api_cleanup_orphan_sessions_by_org(
    org_id: str = Query(..., description="Org ID (string ObjectId from orgs collection)"),
    dry_run: bool = Query(True, description="Default: True (preview only). Set False to delete."),
    limit: Optional[int] = Query(None, description="Optional: cap how many orphans to process")
):
    try:
        report = cleanup_orphan_sessions_by_org(
            org_id=org_id,
            dry_run=dry_run,
            limit=limit
        )
        msg = "Dry run: no deletions performed." if dry_run else "Cleanup completed."
        return api_response(code=HTTP_STATUS.OK, data=report, message=msg)
    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=f"Failed: {e}")

@router.post("/admin/users/dedupe/auto")
async def admin_dedupe_auto(
    dry_run: bool = Query(True, description="Default True: only preview; set False to actually delete"),
    limit_user_ids: Optional[int] = Query(None, description="Optional cap on number of duplicate user_id groups processed"),
):
    try:
        report = dedupe_users_auto(dry_run=dry_run, limit_user_ids=limit_user_ids)
        msg = "Dry run: no deletions performed." if dry_run else "Dedupe completed."
        return api_response(code=HTTP_STATUS.OK, data=report, message=msg)
    except Exception as e:
        return api_response(code=HTTP_STATUS.INTERNAL_SERVER_ERROR, message=f"Failed to dedupe: {e}")

 