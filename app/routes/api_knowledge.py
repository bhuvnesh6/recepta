from flask import Blueprint, request, jsonify, current_app
from bson import ObjectId
from app.extensions import get_db
from app.models import build_knowledge_source, serialize, serialize_many, now
from app.security import login_required, get_scoped_organization_id
from app.services import crawler_service, rag_service, document_service, usage_service
from app.services.storage_service import get_storage_provider

api_knowledge_bp = Blueprint("api_knowledge", __name__, url_prefix="/api/knowledge")

ALLOWED_EXT = {"pdf", "docx", "txt", "csv"}


def _agent_belongs(db, org_id, agent_id):
    return db.agents.find_one({"_id": ObjectId(agent_id), "organization_id": org_id}) is not None


@api_knowledge_bp.get("")
@login_required
def list_sources():
    db = get_db()
    org_id = get_scoped_organization_id()
    agent_id = request.args.get("agent_id")
    q = {"organization_id": org_id}
    if agent_id:
        q["agent_id"] = agent_id
    sources = list(db.knowledge_sources.find(q).sort("created_at", -1))
    return jsonify(serialize_many(sources))


@api_knowledge_bp.post("/website")
@login_required
def add_website():
    db = get_db()
    org_id = get_scoped_organization_id()
    data = request.get_json(force=True)
    agent_id = data.get("agent_id")
    url = (data.get("url") or "").strip()
    if not agent_id or not _agent_belongs(db, org_id, agent_id) or not url:
        return jsonify({"error": "invalid_request"}), 400

    source = build_knowledge_source(org_id, agent_id, "website", source_url=url)
    result = db.knowledge_sources.insert_one(source)
    source_id = str(result.inserted_id)

    cfg = current_app.config
    try:
        urls = crawler_service.discover_urls(url, max_urls=cfg["CRAWL_MAX_URLS"], timeout=cfg["CRAWL_TIMEOUT_SECONDS"])
        relevant = crawler_service.filter_relevant_urls(urls)
        total_chunks = 0
        pages_processed = 0
        for page_url in relevant:
            try:
                title, text = crawler_service.fetch_page_text(page_url, timeout=cfg["CRAWL_TIMEOUT_SECONDS"])
                if not text:
                    continue
                total_chunks += rag_service.index_document(
                    org_id, agent_id, source_id, text,
                    base_metadata={"source_type": "website", "source_url": page_url, "title": title},
                )
                pages_processed += 1
            except Exception:
                continue
        db.knowledge_sources.update_one({"_id": result.inserted_id}, {"$set": {
            "status": "ready", "pages_found": len(relevant), "chunks_created": total_chunks,
            "last_synced_at": now(), "updated_at": now(),
        }})
        usage_service.track(org_id, agent_id, "embedding_ops", total_chunks)
    except Exception as e:
        db.knowledge_sources.update_one({"_id": result.inserted_id},
                                         {"$set": {"status": "failed", "error": str(e), "updated_at": now()}})

    updated = db.knowledge_sources.find_one({"_id": result.inserted_id})
    return jsonify(serialize(updated)), 201


@api_knowledge_bp.post("/upload")
@login_required
def upload_document():
    db = get_db()
    org_id = get_scoped_organization_id()
    agent_id = request.form.get("agent_id")
    file = request.files.get("file")
    if not agent_id or not _agent_belongs(db, org_id, agent_id) or not file:
        return jsonify({"error": "invalid_request"}), 400
    filename = file.filename
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXT:
        return jsonify({"error": "unsupported_file_type"}), 400

    file_bytes = file.read()
    source = build_knowledge_source(org_id, agent_id, ext, file_name=filename)
    result = db.knowledge_sources.insert_one(source)
    source_id = str(result.inserted_id)

    try:
        storage = get_storage_provider()
        storage_path = f"{org_id}/{agent_id}/{source_id}_{filename}"
        url = storage.upload(storage_path, file_bytes, content_type=file.mimetype)

        text = document_service.extract_text(file_bytes, filename)
        chunks = rag_service.index_document(org_id, agent_id, source_id, text,
                                             base_metadata={"source_type": ext, "title": filename})
        db.knowledge_sources.update_one({"_id": result.inserted_id}, {"$set": {
            "status": "ready", "chunks_created": chunks, "storage_path": url,
            "last_synced_at": now(), "updated_at": now(),
        }})
        usage_service.track(org_id, agent_id, "embedding_ops", chunks)
    except Exception as e:
        db.knowledge_sources.update_one({"_id": result.inserted_id},
                                         {"$set": {"status": "failed", "error": str(e), "updated_at": now()}})

    updated = db.knowledge_sources.find_one({"_id": result.inserted_id})
    return jsonify(serialize(updated)), 201


@api_knowledge_bp.post("/<source_id>/resync")
@login_required
def resync_source(source_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    source = db.knowledge_sources.find_one({"_id": ObjectId(source_id), "organization_id": org_id})
    if not source or source["source_type"] != "website":
        return jsonify({"error": "not_resyncable"}), 400
    rag_service.delete_source_chunks(org_id, source["agent_id"], source_id)
    cfg = current_app.config
    urls = crawler_service.discover_urls(source["source_url"], max_urls=cfg["CRAWL_MAX_URLS"])
    relevant = crawler_service.filter_relevant_urls(urls)
    total_chunks = 0
    for page_url in relevant:
        try:
            title, text = crawler_service.fetch_page_text(page_url)
            total_chunks += rag_service.index_document(org_id, source["agent_id"], source_id, text,
                                                         base_metadata={"source_url": page_url, "title": title})
        except Exception:
            continue
    db.knowledge_sources.update_one({"_id": ObjectId(source_id)}, {"$set": {
        "chunks_created": total_chunks, "pages_found": len(relevant), "last_synced_at": now(), "updated_at": now(),
    }})
    updated = db.knowledge_sources.find_one({"_id": ObjectId(source_id)})
    return jsonify(serialize(updated))


@api_knowledge_bp.delete("/<source_id>")
@login_required
def delete_source(source_id):
    db = get_db()
    org_id = get_scoped_organization_id()
    source = db.knowledge_sources.find_one({"_id": ObjectId(source_id), "organization_id": org_id})
    if not source:
        return jsonify({"error": "not_found"}), 404
    rag_service.delete_source_chunks(org_id, source["agent_id"], source_id)
    db.knowledge_sources.delete_one({"_id": ObjectId(source_id)})
    return jsonify({"deleted": True})
