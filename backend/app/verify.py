# verify.py
# Checks the LLM's extracted findings against the real PDF text.
# The LLM can get page numbers wrong or change a passage, so we confirm it here.

import re
import unicodedata


def clean(text):
    # Keep only lowercase letters and digits, so small differences
    # (line breaks, hyphens, fancy characters like "ﬁ") don't break the match
    text = unicodedata.normalize("NFKC", text).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def find_page(passage, llm_page, page_text):
    # Return the page the passage is really on (or None if it isn't found)
    if passage == "":
        return None

    # Check the page the LLM gave first
    if llm_page in page_text and passage in page_text[llm_page]:
        return llm_page

    # Otherwise search every page
    for number, text in page_text.items():
        if passage in text:
            return number

    return None


def verify_findings(findings, pages):
    # Cleaned text of every page, like {1: "...", 2: "..."}
    page_text = {}
    for p in pages:
        page_text[p["page"]] = clean(p["text"])

    # Gather every extracted item, along with the field its passage should mention
    items = []
    if isinstance(findings.get("research_task"), dict):
        items.append((findings["research_task"], "value"))

    for key in ["datasets", "methods", "evaluation_metrics"]:
        for item in findings.get(key, []):
            items.append((item, "name"))

    for item in findings.get("results", []):
        items.append((item, "value"))

    found = 0
    mentioned = 0
    corrected = 0

    for item, field in items:
        passage = clean(item.get("passage", ""))
        llm_page = item.get("page")
        real_page = find_page(passage, llm_page, page_text)

        # Was the passage found in the PDF at all?
        item["passage_found"] = real_page is not None
        if real_page is not None:
            found += 1

            # Fix the page number if the LLM got it wrong (keep its answer too)
            if real_page != llm_page:
                corrected += 1
                item["page_llm"] = llm_page
                item["page"] = real_page

        # Does the passage mention the name (or value) it is supposed to support?
        thing = clean(str(item.get(field, "")))
        item["mentioned_in_passage"] = thing != "" and thing in passage
        
        if item["mentioned_in_passage"]:
            mentioned += 1

    # Summary numbers (these are the "X of Y verified" for the video)
    return {
        "items_checked": len(items),
        "passage_found": found,
        "mentioned_in_passage": mentioned,
        "pages_corrected": corrected,
    }