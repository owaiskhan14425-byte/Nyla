# services/dedupe_auto.py
from datetime import datetime
from typing import Dict, Any, List, Optional
from pymongo import DeleteOne
from services.mongo_client import db
from typing import Dict, Any, List, Optional
from services.mongo_client import db
from bson import ObjectId

SESSIONS_COLL_NAME = "sessions"
USERS_COLL_NAME = "users"
ORGS_COLL_NAME = "organization"


def _get_logs_collection_name_for_org(org_id: str) -> str:
    """
    Fetch the logs collection name for a given org_id from the orgs collection.
    Expects a document with `collectionName`.
    """
    org_collection  = db[ORGS_COLL_NAME]
    org_doc = org_collection.find_one({"_id": org_id}) or org_collection.find_one({"_id": ObjectId(org_id)},
        {"collectionName": 1}
    )
    if not org_doc or not org_doc.get("collectionName"):
        raise ValueError(f"Logs collection not found for org_id={org_id}. Make sure org exists and has 'collectionName'.")
    return org_doc["collectionName"]

def cleanup_orphan_sessions_by_org(
    org_id: str,
    dry_run: bool = True,
    limit: Optional[int] = None,  # optionally cap how many to process in one run
) -> Dict[str, Any]:
    """
    For the given org_id:
      - Find sessions in `sessions` with that org_id
      - Look for matching history in the org's logs collection (using session_id)
      - "History" means at least one log doc exists with that session_id and
        one of {message_id, question, answer} present
      - If history not found → the session is an "orphan"
      - Optionally delete orphans.

    Returns a summary with totals and a sample of the orphan sessions.
    """
    logs_collection = _get_logs_collection_name_for_org(org_id)
    sessions = db[SESSIONS_COLL_NAME]

    # For totals:
    total_sessions_for_org = sessions.count_documents({"org_id": org_id})

    # We use $lookup with a pipeline to ensure we only count logs that are "real" chat history
    pipeline: List[Dict[str, Any]] = [
        {"$match": {"org_id": org_id}},
        {
            "$lookup": {
                "from": logs_collection,
                "let": {"sid": "$session_id"},
                "pipeline": [
                    {"$match": {"$expr": {"$eq": ["$session_id", "$$sid"]}}},
                    # Treat a log as valid "history" only if it has one of these fields
                    {"$match": {
                        "$or": [
                            {"message_id": {"$exists": True}},
                            {"question": {"$exists": True}},
                            {"answer": {"$exists": True}},
                        ]
                    }},
                    {"$limit": 1}
                ],
                "as": "history"
            }
        },
        {"$match": {"history": {"$size": 0}}},     # only orphans
        {"$project": {"_id": 1, "session_id": 1}},
    ]

    if limit:
        pipeline.append({"$limit": int(limit)})

    orphans = list(sessions.aggregate(pipeline))
    to_delete_ids = [o["_id"] for o in orphans]
    to_delete_count = len(to_delete_ids)

    # Compute total sessions WITH and WITHOUT history (for the org)
    # (This second pass is optional; it’s nice for a complete summary.)
    with_history_count = sessions.count_documents({
        "org_id": org_id,
        "session_id": {"$in": db[logs_collection].distinct("session_id")}
    })
    without_history_count = total_sessions_for_org - with_history_count

    summary: Dict[str, Any] = {
        "org_id": org_id,
        "logs_collection": logs_collection,
        "dry_run": dry_run,
        "totals": {
            "total_sessions_for_org": total_sessions_for_org,
            "total_sessions_with_history": with_history_count,
            "total_sessions_without_history": without_history_count
        },
        "to_delete_count": to_delete_count,
        "sample": [
            {"_id": str(doc["_id"]), "session_id": doc.get("session_id")}
            for doc in orphans[:10]  # preview
        ]
    }

    if dry_run or not to_delete_ids:
        summary["deleted_count"] = 0
        return summary

    # Delete orphans
    ops = [DeleteOne({"_id": _id}) for _id in to_delete_ids]
    bulk_res = sessions.bulk_write(ops, ordered=False) if ops else None
    summary["deleted_count"] = bulk_res.deleted_count if bulk_res else 0
    return summary


def dedupe_users_auto(
    dry_run: bool = True,
    limit_user_ids: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Auto-detect duplicates by user_id across the entire 'users' collection.
    Keep newest (updated_at desc, created_at desc, _id desc),
    delete all older ones.
    """

    coll = db[USERS_COLL_NAME]

    total_docs = coll.count_documents({})
    distinct_user_ids = coll.distinct("user_id")
    total_distinct_user_ids = len(distinct_user_ids)

    pipeline: List[Dict[str, Any]] = [
        # Normalize date fields
        {"$addFields": {
            "updatedAt": {"$ifNull": ["$updated_at", datetime(1, 1, 1)]},
            "createdAt": {"$ifNull": ["$created_at", datetime(1, 1, 1)]},
        }},
        {"$sort": {"updatedAt": -1, "createdAt": -1, "_id": -1}},
        {"$group": {
            "_id": "$user_id",
            "keep": {"$first": "$_id"},         # newest one
            "all_ids": {"$push": "$_id"},
            "count": {"$sum": 1}
        }},
        {"$match": {"count": {"$gt": 1}}},
        # FIX: return all except the first (instead of just the first)
        {"$project": {
            "_id": 0,
            "user_id": "$_id",
            "keep": 1,
            "to_delete": {"$slice": ["$all_ids", 1, {"$size": "$all_ids"}]},
            "count": 1
        }},
    ]

    if limit_user_ids:
        pipeline.append({"$limit": int(limit_user_ids)})

    dup_groups = list(coll.aggregate(pipeline))

    to_delete_ids: List[Any] = []
    total_repeated_user_ids = 0
    total_duplicates_to_delete = 0

    for grp in dup_groups:
        total_repeated_user_ids += 1
        dels = grp.get("to_delete", []) or []
        total_duplicates_to_delete += len(dels)
        to_delete_ids.extend(dels)

    summary: Dict[str, Any] = {
        "dry_run": dry_run,
        "totals": {
            "total_docs_scanned": total_docs,
            "total_distinct_user_ids": total_distinct_user_ids,
            "total_repeated_user_ids": total_repeated_user_ids,
            "total_duplicates_to_delete": total_duplicates_to_delete,
        },
        "sample": [
            {
                "user_id": grp["user_id"],
                "keep": str(grp["keep"]),
                "to_delete_count": len(grp["to_delete"]),
                "to_delete_list": [str(x) for x in grp["to_delete"]],
            }
            for grp in dup_groups[:10]  # preview first 10 groups
        ],
    }

    if dry_run or not to_delete_ids:
        summary["deleted_count"] = 0
        return summary

    ops = [DeleteOne({"_id": _id}) for _id in to_delete_ids]
    bulk_res = coll.bulk_write(ops, ordered=False) if ops else None
    summary["deleted_count"] = bulk_res.deleted_count if bulk_res else 0
    return summary

