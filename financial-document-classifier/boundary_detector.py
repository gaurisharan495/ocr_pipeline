# ============================================================
# boundary_detector.py
# Approach B — Two Pass Boundary Detection System
# Pass 1: Detects where new documents start
# Pass 2: Classifies each segment using combined page text
# ============================================================

import re
import json
import os

OCR_RESULTS_FILE = "outputs/ocr_results.json"
OUTPUT_FILE = "outputs/segments.json"

# ============================================================
# DOCUMENT TITLES
# Only specific multi-word phrases — no single generic words
# ============================================================
DOCUMENT_TITLES = {
    "tax_invoice":             ["tax invoice"],
    "eway_bill":               ["e-way bill", "eway bill", "e way bill"],
    "purchase_order":          ["purchase order"],
    "qcr_finished_goods":      ["quality check report", "qcr",
                                "finished goods inspection", "quality check"],
    "goods_receipt_note":      ["goods receipt note", "goods received note",
                                "material receipt note", "grn"],
    "job_work_order":          ["job work order", "job order", "work order"],
    "snag_list_certificate":   ["snag list certificate", "snag list"],
    "invoice_cash_memo":       ["cash memo", "cash invoice", "retail invoice"],
    "ap_tracker":              ["ap tracker", "po tracker",
                                "accounts payable tracker"],
    "credit_note":             ["credit note"],
    "delivery_challan":        ["delivery challan"],
    "manual_delivery_receipt": ["delivery receipt", "proof of delivery"]
}

# ============================================================
# DEFINITIVE REGEX PATTERNS
# Near-certain structural proof of document type
# ============================================================
DEFINITIVE_PATTERNS = {
    "tax_invoice": [
        r"\b\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}\b",
        r"(CGST|SGST|IGST)\s*@?\s*\d+(\.\d+)?\s*%",
    ],
    "eway_bill": [
        r"EWB[\s\-\/]?\d{4,}",
        r"\b[A-Z]{2}\s?\d{2}\s?[A-Z]{1,2}\s?\d{4}\b",
    ],
    "goods_receipt_note": [
        r"\bGRN[\s\-\/]?\d+\b",
        r"GRN\s*NO",
    ],
    "purchase_order": [
        r"\bP\.?O\.?\s*(no|num|number|#)[\s\-:]{0,3}\d+\b",
    ],
    "job_work_order": [
        r"\bJWO[\s\-\/]?\d+\b",
        r"JW\s*ORDER\s*(no|num|#)?[\s\-:]{0,3}\d+"
    ],
    "credit_note": [
        r"\bCN[\s\-\/]?\d+\b",
    ],
    "delivery_challan": [
        r"\bDC[\s\-\/]?(no|num)?[\s\-:]{0,3}\d+\b",
        r"CHALLAN\s*(no|num|#)?[\s\-:]{0,3}\d+"
    ],
    "ap_tracker": [
        r"(ord|recd|rej|bal)[\s\.]*qty",
        r"(prepared\s*by).{0,30}(verified\s*by)"
    ]
}

# ============================================================
# SEGMENT KEYWORDS
# Used in Pass 2 only for segment classification
# ============================================================
SEGMENT_KEYWORDS = {
    "tax_invoice": [
        "tax invoice", "gstin", "hsn", "cgst", "sgst", "igst",
        "taxable value", "place of supply", "invoice no"
    ],
    "eway_bill": [
        "e-way bill", "eway", "ewb", "vehicle no",
        "transporter", "validity", "consigner", "consignee"
    ],
    "purchase_order": [
        "purchase order", "po no", "vendor",
        "delivery date", "ship to", "bill to", "order date"
    ],
    "qcr_finished_goods": [
        "quality check", "qcr", "finished goods",
        "inspection", "dimension", "surface", "batch", "inspector"
    ],
    "goods_receipt_note": [
        "goods receipt", "grn", "material received",
        "received by", "quantity received", "shortage", "damage"
    ],
    "job_work_order": [
        "job work", "work order", "jwo", "labour",
        "fabrication", "contractor", "scope of work", "process"
    ],
    "snag_list_certificate": [
        "snag list", "snag", "certificate",
        "defect", "rectification", "completion", "punch list"
    ],
    "invoice_cash_memo": [
        "cash memo", "cash invoice", "retail", "memo no"
    ],
    "ap_tracker": [
        "ap tracker", "ord qty", "recd qty", "rej qty",
        "prepared by", "verified by", "tracker",
        "total order", "balance qty"
    ],
    "credit_note": [
        "credit note", "cn no", "return",
        "against invoice", "credit amount"
    ],
    "delivery_challan": [
        "delivery challan", "challan no", "dc no",
        "for delivery", "delivery note"
    ],
    "manual_delivery_receipt": [
        "delivery receipt", "proof of delivery", "pod",
        "received in good condition", "receiver signature"
    ]
}


# ============================================================
# PASS 1 HELPERS
# ============================================================

def get_title_zone_text(page_data):
    """
    Gets text from top 20% of page using bounding boxes.
    Falls back to header_text if no bounding box data.
    """
    text_blocks = page_data.get("text_blocks", [])
    page_height = page_data.get("page_height", 0)

    if text_blocks and page_height > 0:
        cutoff = page_height * 0.20
        title_words = [
            b["text"] for b in text_blocks
            if b.get("y", 9999) <= cutoff
        ]
        if title_words:
            return " ".join(title_words).lower()

    return page_data.get("header_text", "").lower()


def check_title(page_data):
    """
    Checks if a known document title appears in title zone.
    Longer phrases matched first (more specific).
    """
    title_text = get_title_zone_text(page_data)
    if not title_text:
        return None, 0.0

    all_titles = []
    for doc_type, phrases in DOCUMENT_TITLES.items():
        for phrase in phrases:
            all_titles.append((len(phrase), phrase, doc_type))
    all_titles.sort(reverse=True)

    for _, phrase, doc_type in all_titles:
        if phrase in title_text:
            return doc_type, 0.90

    return None, 0.0


def check_patterns(text):
    """
    Checks for definitive regex patterns.
    Returns first match found.
    """
    if not text:
        return None, 0.0
    for doc_type, patterns in DEFINITIVE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return doc_type, 0.85
    return None, 0.0


def check_document_number(page_data):
    """
    Checks if a document reference number appears on this page.
    INV/2024/001, GRN-45, PO/123, DC/2024/05 etc.
    """
    title_text = get_title_zone_text(page_data)
    full_text = page_data.get("full_text", "")
    pattern = r"\b(inv|grn|po|dc|cn|jwo|ewb|wo)[\s\-\/\\]{0,2}\d+"

    if re.search(pattern, title_text, re.IGNORECASE):
        return True
    if re.search(pattern, full_text[:200], re.IGNORECASE):
        return True
    return False


def check_date_in_title_zone(page_data):
    """Checks if a date appears in the title zone."""
    title_text = get_title_zone_text(page_data)
    date_patterns = [
        r"\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}",
        r"\d{1,2}\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}",
    ]
    for pattern in date_patterns:
        if re.search(pattern, title_text, re.IGNORECASE):
            return True
    return False


# ============================================================
# PASS 1 — BOUNDARY DETECTION
# ============================================================

def detect_boundary(page_data, previous_label):
    """
    Determines if a new document starts on this page.

    Decision priority:
    1. Too few words → continuation
    2. Title found in title zone → new document
    3. Definitive regex pattern found → new document
    4. Document number present → likely new document
    5. Nothing found → continuation
    """
    if not page_data:
        return {
            "is_boundary": False,
            "document_type": previous_label,
            "confidence": 0.0,
            "reason": "Empty page data"
        }

    word_count = page_data.get("word_count", 0)

    # Fast exit — too few words
    if word_count < 10:
        return {
            "is_boundary": False,
            "document_type": previous_label,
            "confidence": 0.0,
            "reason": f"Too few words ({word_count}) — continuation"
        }

    try:
        title_type, title_conf = check_title(page_data)
    except Exception as e:
        title_type, title_conf = None, 0.0

    full_text = page_data.get("full_text", "")

    try:
        pattern_type, pattern_conf = check_patterns(full_text)
    except Exception as e:
        pattern_type, pattern_conf = None, 0.0

    try:
        has_doc_number = check_document_number(page_data)
    except Exception:
        has_doc_number = False

    try:
        has_date = check_date_in_title_zone(page_data)
    except Exception:
        has_date = False

    # ---- Decision ----

    # Title found — strongest signal
    if title_type and title_conf >= 0.85:
        if title_type == previous_label and not has_doc_number:
            return {
                "is_boundary": False,
                "document_type": previous_label,
                "confidence": title_conf,
                "reason": "Same type, no new doc number — continuation"
            }
        return {
            "is_boundary": True,
            "document_type": title_type,
            "confidence": title_conf,
            "reason": f"Title found: {title_type}"
        }

    # Pattern match — strong signal
    if pattern_type and pattern_conf >= 0.80:
        if pattern_type != previous_label:
            return {
                "is_boundary": True,
                "document_type": pattern_type,
                "confidence": pattern_conf,
                "reason": f"Pattern match: {pattern_type}"
            }
        if has_doc_number and has_date:
            return {
                "is_boundary": True,
                "document_type": pattern_type,
                "confidence": 0.75,
                "reason": f"Same type, new doc number + date: {pattern_type}"
            }

    # Doc number present
    if has_doc_number:
        inferred = pattern_type or title_type or previous_label
        return {
            "is_boundary": True,
            "document_type": inferred,
            "confidence": 0.60,
            "reason": f"Doc number found, inferred: {inferred}"
        }

    # Not enough evidence
    return {
        "is_boundary": False,
        "document_type": previous_label,
        "confidence": 0.0,
        "reason": "Insufficient evidence — continuation"
    }


# ============================================================
# PASS 2 — SEGMENT CLASSIFICATION
# ============================================================

def classify_segment(pages_in_segment, boundary_type=None,
                     boundary_conf=0.0):
    """
    Classifies a complete document segment.
    Combines ALL page text before classifying.

    Tier 1 — Definitive regex patterns
    Tier 2 — Trust boundary detector if high confidence title
    Tier 3 — Keyword presence scoring on combined text
    """
    combined_text = " ".join([
        p.get("full_text", "") for p in pages_in_segment
    ]).lower()

    first_header = ""
    if pages_in_segment:
        first_header = pages_in_segment[0].get(
            "header_text", ""
        ).lower()

    if not combined_text.strip():
        return boundary_type or "unknown", 0.0

    # Tier 1 — definitive patterns
    pattern_type, pattern_conf = check_patterns(combined_text)
    if pattern_type:
        return pattern_type, pattern_conf

    # Tier 2 — high confidence boundary title
    if boundary_type and boundary_conf >= 0.88:
        return boundary_type, boundary_conf

    # Tier 3 — keyword presence scoring
    scores = {}
    for doc_type, keywords in SEGMENT_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in first_header:
                score += 3
            if kw in combined_text:
                score += 1
        scores[doc_type] = score

    best_type = max(scores, key=scores.get)
    best_score = scores[best_type]

    if best_score == 0:
        return boundary_type or "unknown", 0.2

    confidence = min(best_score / 10.0, 1.0)
    if best_type == boundary_type:
        confidence = min(confidence + 0.15, 1.0)

    return best_type, round(confidence, 3)


# ============================================================
# MAIN — Two Pass Pipeline
# ============================================================

def run_boundary_detection():
    with open(OCR_RESULTS_FILE, "r", encoding="utf-8") as f:
        ocr_results = json.load(f)

    all_segments = {}

    for pdf_name, pages_data in ocr_results.items():
        print(f"\n{'='*60}")
        print(f"PDF: {pdf_name.upper()}")
        print(f"{'='*60}")

        if not isinstance(pages_data, list):
            pages_data = [pages_data]

        # ---- PASS 1: Find boundaries ----
        print("\n  PASS 1 — Boundary Detection:")
        raw_segments = []
        current_pages = []
        current_type = "unknown"
        current_conf = 0.0
        previous_label = "unknown"

        for page_data in pages_data:
            page_num = page_data.get("page_number", 0)
            decision = detect_boundary(page_data, previous_label)

            print(f"    Page {page_num}: "
                  f"{'NEW' if decision['is_boundary'] else 'cont':<5} | "
                  f"{decision['document_type']:<25} | "
                  f"{decision['reason']}")

            if decision["is_boundary"] or not current_pages:
                if current_pages:
                    raw_segments.append({
                        "pages_data": current_pages,
                        "boundary_type": current_type,
                        "boundary_confidence": current_conf,
                        "start_page": current_pages[0]["page_number"],
                        "end_page": current_pages[-1]["page_number"]
                    })
                current_pages = [page_data]
                current_type = decision["document_type"]
                current_conf = decision["confidence"]
            else:
                current_pages.append(page_data)

            previous_label = decision["document_type"]

        if current_pages:
            raw_segments.append({
                "pages_data": current_pages,
                "boundary_type": current_type,
                "boundary_confidence": current_conf,
                "start_page": current_pages[0]["page_number"],
                "end_page": current_pages[-1]["page_number"]
            })

        # ---- PASS 2: Classify each segment ----
        print("\n  PASS 2 — Segment Classification:")
        final_segments = []

        for seg in raw_segments:
            final_type, conf = classify_segment(
                seg["pages_data"],
                boundary_type=seg["boundary_type"],
                boundary_conf=seg["boundary_confidence"]
            )

            pages_str = (
                f"Page {seg['start_page']}"
                if seg["start_page"] == seg["end_page"]
                else f"Pages {seg['start_page']}–{seg['end_page']}"
            )
            print(f"    {pages_str}: {final_type} (conf: {conf})")

            final_segments.append({
                "document_type": final_type,
                "start_page": seg["start_page"],
                "end_page": seg["end_page"],
                "page_count": seg["end_page"] - seg["start_page"] + 1,
                "confidence": conf,
                "boundary_type": seg["boundary_type"]
            })

        all_segments[pdf_name] = final_segments

        print(f"\n  SEGMENTS — {pdf_name.upper()}:")
        for seg in final_segments:
            pages = (f"Page {seg['start_page']}"
                     if seg["start_page"] == seg["end_page"]
                     else f"Pages {seg['start_page']}–{seg['end_page']}")
            print(f"    {pages} → {seg['document_type']} "
                  f"(conf: {seg['confidence']})")

    os.makedirs("outputs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_segments, f, indent=2)

    print(f"\nSegments saved → {OUTPUT_FILE}")
    return all_segments


if __name__ == "__main__":
    print("=" * 60)
    print("Boundary Detector v2 — Two Pass System")
    print("=" * 60)
    run_boundary_detection()
