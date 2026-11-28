# main.py
# Entry point for the PaperCuts backend.
# It creates the server and defines the endpoints the frontend will call.

import hashlib
import json
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.extraction import extract_findings
from app.pdf_reader import extract_pages
from app.rules import compare_results
from app.verify import verify_findings

# Create the app. Run it with: uvicorn app.main:app --reload
app = FastAPI(title = "PaperCuts API")

# Needed so the React app (running on a different port) can call this API
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:3000", "http://localhost:5173"],
    allow_methods = ["*"],
    allow_headers = ["*"]
)

# Folder where uploaded PDFs are saved (created if it does not exist yet)
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents = True, exist_ok = True)

# Folder where extracted findings are saved, so we only pay for each paper once
FINDINGS_DIR = Path("data/findings")
FINDINGS_DIR.mkdir(parents = True, exist_ok = True)

# Uploaded papers stored in memory for now (lost on restart), will use MongoDB later
papers = {}


# ---------- Data shapes ----------

# What the frontend sends: a question and which papers to use
class ChatRequest(BaseModel):
    question: str
    paper_ids: list[str]


# Points to where an answer came from in a paper (for citations)
class SourceRef(BaseModel):
    paper_id: str
    page: int | None = None
    passage: str | None = None


# What we send back: answer, comparison label, reasons, and sources
class ChatResponse(BaseModel):
    answer: str
    comparison_status: str | None = None
    reasons: list[str] = []
    sources: list[SourceRef] = []


# ---------- Endpoints ----------

@app.get("/health")
def health():
    # Just to check the server is up
    return {"status": "ok"}


@app.post("/api/papers/upload")
async def upload_paper(file: UploadFile = File(...)):
    # Only accept PDFs
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code = 400, detail = "Only PDF files are accepted.")

    # Make the ID from the file's contents, so the same PDF always gets the same ID
    contents = await file.read()
    paper_id = hashlib.sha256(contents).hexdigest()[:8]
    save_path = UPLOAD_DIR / f"{paper_id}.pdf"
    save_path.write_bytes(contents)

    # Read the text page by page (fails if the file isn't a real PDF)
    try:
        pages = extract_pages(str(save_path))
        
    except Exception:
        save_path.unlink(missing_ok = True)
        raise HTTPException(status_code = 400, detail = "Could not read this PDF.")

    # Keep track of the paper (and its text) so we can use it later
    papers[paper_id] = {
        "id": paper_id,
        "filename": file.filename,
        "path": str(save_path),
        "pages": pages,
    }

    # TODO: chunk and embed the text (Path A)
    return {
        "id": paper_id,
        "filename": file.filename,
        "num_pages": len(pages),
        "status": "uploaded",
    }


@app.get("/api/papers")
def list_papers():
    # Return the ID and filename of every uploaded paper
    return [{"id": p["id"], "filename": p["filename"]} for p in papers.values()]


@app.get("/api/papers/{paper_id}/text")
def get_paper_text(paper_id: str):
    # For testing: see the text the PDF reader pulled out, page by page
    paper = papers.get(paper_id)

    if paper is None:
        raise HTTPException(status_code = 404, detail = "Paper not found.")

    return {"id": paper_id, "pages": paper["pages"]}


@app.post("/api/papers/{paper_id}/extract")
def extract_paper(paper_id: str, force: bool = False):
    # Run the LLM extraction on one uploaded paper and save the findings
    paper = papers.get(paper_id)

    if paper is None:
        raise HTTPException(status_code = 404, detail = "Paper not found.")

    cache_file = FINDINGS_DIR / f"{paper_id}.json"

    # Use the saved result if we already paid for this paper (unless force = true)
    if cache_file.exists() and not force:
        findings = json.loads(cache_file.read_text(encoding = "utf-8"))
    
    else:

        try:
            findings = extract_findings(paper["pages"])

        except Exception as e:
            raise HTTPException(status_code = 500, detail = f"Extraction failed: {e}")
        
        cache_file.write_text(json.dumps(findings, indent = 2), encoding = "utf-8")

    # Check the findings against the real PDF text (also fixes page numbers)
    findings["verification"] = verify_findings(findings, paper["pages"])

    paper["findings"] = findings
    return findings


@app.get("/api/compare/results")
def compare_two_results(paper_a: str, index_a: int, paper_b: str, index_b: int):
    # For testing the rules: compare one result from paper A with one from paper B
    # (index is the position in the paper's results list, starting at 0)
    paper_1 = papers.get(paper_a)
    paper_2 = papers.get(paper_b)

    if paper_1 is None or paper_2 is None:
        raise HTTPException(status_code = 404, detail = "Paper not found.")
    
    if "findings" not in paper_1 or "findings" not in paper_2:
        raise HTTPException(status_code = 400, detail = "Run extract on both papers first.")

    try:
        result_a = paper_1["findings"]["results"][index_a]
        result_b = paper_2["findings"]["results"][index_b]

    except IndexError:
        raise HTTPException(status_code = 404, detail = "No result at that index.")

    task_a = paper_1["findings"].get("research_task", {}).get("value", "not reported")
    task_b = paper_2["findings"].get("research_task", {}).get("value", "not reported")

    return {
        "result_a": result_a,
        "result_b": result_b,
        "comparison": compare_results(task_a, result_a, task_b, result_b),
    }


@app.delete("/api/papers/{paper_id}")
def delete_paper(paper_id: str):
    # Take the paper out of the list (None if the ID isn't found)
    paper = papers.pop(paper_id, None)

    if paper is None:
        raise HTTPException(status_code = 404, detail = "Paper not found.")

    # Delete the saved PDF too
    Path(paper["path"]).unlink(missing_ok = True)
    return {"deleted": paper_id}


@app.post("/api/chat", response_model = ChatResponse)
def chat(req: ChatRequest):
    # TODO: retrieve passages, run the rule engine, generate an answer with citations
    return ChatResponse(answer = "Placeholder answer. Pipeline not built yet.")


@app.post("/api/compare", response_model = ChatResponse)
def compare(req: ChatRequest):
    # TODO: look up findings in the knowledge graph and run the comparison rules
    return ChatResponse(
        answer = "Placeholder comparison.",
        comparison_status = "not_enough_information",
        reasons = ["Rule engine not built yet."],
    )