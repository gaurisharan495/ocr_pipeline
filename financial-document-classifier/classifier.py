# ============================================================
# classifier.py
# Approach A — Keyword Scoring Classifier
# Classifies individual pages using fuzzy keyword matching
# ============================================================

import json
import os
import pandas as pd
from fuzzywuzzy import fuzz
from collections import defaultdict

# ---- CONFIGURATION ----
OCR_RESULTS_FILE = "outputs/ocr_results.json"
LABELS_FILE = "data/labels.csv"
OUTPUT_FILE = "outputs/predictions.json"

# Thresholds
FUZZY_THRESHOLD = 80
HEADER_WEIGHT = 3
LOW_OCR_THRESHOLD = 10
REVIEW_THRESHOLD = 0.3
MAX_SCORE_NORMALIZER = 8.0

DOCUMENT_FAMILIES = {
    "job_work_order": "work_documents",
    "purchase_order": "work_documents",
    "goods_receipt_note": "receipt_documents",
    "manual_delivery_receipt": "receipt_documents",
    "delivery_challan": "receipt_documents",
    "tax_invoice": "invoice_documents",
    "invoice_cash_memo": "invoice_documents",
    "credit_note": "invoice_documents",
    "ap_tracker": "tracking_documents",
    "eway_bill": "transit_documents",
    "qcr_finished_goods": "quality_documents",
    "snag_list_certificate": "quality_documents"
}

SAME_FAMILY_THRESHOLD = 3

# ---- KEYWORD DICTIONARY ----
KEYWORDS = {
    "tax_invoice": [
        "tax invoice", "gstin", "hsn", "cgst", "sgst", "igst",
        "invoice no", "invoice date", "taxable value",
        "place of supply", "gst"
    ],
    "eway_bill": [
        "e-way bill", "eway bill", "ewb no", "ewb",
        "vehicle no", "transporter", "validity",
        "consigner", "consignee"
    ],
    "purchase_order": [
        "purchase order", "p.o. no", "po number",
        "order date", "delivery date", "vendor",
        "ship to", "bill to", "po no", "purchase"
    ],
    "qcr_finished_goods": [
        "quality check report", "qcr", "finished goods",
        "inspection", "dimension", "surface finish",
        "batch no", "inspector", "qc passed"
    ],
    "goods_receipt_note": [
        "goods receipt note", "grn", "material received",
        "received by", "quantity received",
        "shortage", "damage", "grn no"
    ],
    "job_work_order": [
        "job work order", "job work", "jwo", "labour",
        "fabrication", "contractor", "scope of work",
        "process", "work completion"
    ],
    "snag_list_certificate": [
        "snag list certificate", "snag list", "snag",
        "certificate", "defect", "rectification",
        "completion", "punch list"
    ],
    "invoice_cash_memo": [
        "cash memo", "cash invoice", "retail invoice",
        "memo no", "cash sale"
    ],
    "ap_tracker": [
        "ap tracker", "ord qty", "recd qty", "rej qty",
        "prepared by", "verified by", "tracker",
        "total order", "balance qty", "move qty"
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

NEGATIVE_KEYWORDS = {
    "tax_invoice": [
        "challan", "credit note", "job work",
        "ord qty", "recd qty", "tracker"
    ],
    "eway_bill": [
        "invoice no", "credit note", "purchase order",
        "job work", "snag", "receipt"
    ],
    "purchase_order": [
        "challan", "credit note", "snag",
        "job work", "goods receipt", "cash memo"
    ],
    "qcr_finished_goods": [
        "invoice", "challan", "credit note", "eway"
    ],
    "goods_receipt_note": [
        "invoice no", "credit note", "snag",
        "eway", "job work", "cash memo"
    ],
    "job_work_order": [
        "challan", "credit note", "snag",
        "eway", "cash memo"
    ],
    "snag_list_certificate": [
        "invoice", "eway", "purchase order",
        "challan", "goods receipt", "credit"
    ],
    "invoice_cash_memo": [
        "gstin", "hsn", "cgst", "eway",
        "challan", "snag", "job work"
    ],
    "ap_tracker": [
        "challan", "snag", "credit note",
        "eway", "cash memo"
    ],
    "credit_note": [
        "challan", "eway", "job work",
        "snag", "purchase order", "cash memo"
    ],
    "delivery_challan": [
        "invoice no", "credit note", "snag",
        "eway", "job work", "cash memo", "gstin"
    ],
    "manual_delivery_receipt": [
        "invoice no", "gstin", "credit note",
        "eway", "job work", "snag", "challan no"
    ]
}


# ============================================================
# FUZZY MATCHING
# ============================================================

def fuzzy_match_keyword(text, keyword, threshold=FUZZY_THRESHOLD):
    if not text or not keyword:
        return False
    if keyword in text:
        return True
    similarity = fuzz.token_set_ratio(keyword, text)
    return similarity >= threshold


# ============================================================
# SCORING
# ============================================================

def score_document(ocr_data):
    """
    Scores a page against all 12 document categories.
    Header keywords worth 3x body keywords.
    Negative keywords apply penalty.
    """
    full_text = ocr_data.get("full_text", "")
    header_text = ocr_data.get("header_text", "")
    scores = {}

    for category, keywords_list in KEYWORDS.items():
        score = 0

        for keyword in keywords_list:
            if fuzzy_match_keyword(header_text, keyword):
                score += HEADER_WEIGHT
            if fuzzy_match_keyword(full_text, keyword):
                score += 1

        for neg_kw in NEGATIVE_KEYWORDS.get(category, []):
            if fuzzy_match_keyword(full_text, neg_kw):
                score -= 2

        scores[category] = max(score, 0)

    return scores


# ============================================================
# PAGE PREDICTION
# ============================================================

def predict_page(ocr_data):
    word_count = ocr_data.get("word_count", 0)

    if word_count < LOW_OCR_THRESHOLD:
        return {
            "predicted_label": "NEEDS_INHERITANCE",
            "confidence": 0.0,
            "scores": {},
            "flagged_for_review": False,
            "needs_inheritance": True,
            "word_count": word_count,
            "reason": f"Only {word_count} words — too little text"
        }

    scores = score_document(ocr_data)
    max_score = max(scores.values())
    top_category = max(scores, key=scores.get)

    if max_score == 0:
        return {
            "predicted_label": "NEEDS_INHERITANCE",
            "confidence": 0.0,
            "scores": scores,
            "flagged_for_review": True,
            "needs_inheritance": True,
            "word_count": word_count,
            "reason": "No keywords matched"
        }

    confidence = min(max_score / MAX_SCORE_NORMALIZER, 1.0)
    flagged = confidence < REVIEW_THRESHOLD

    return {
        "predicted_label": top_category,
        "confidence": round(confidence, 3),
        "scores": scores,
        "flagged_for_review": flagged,
        "needs_inheritance": False,
        "word_count": word_count,
        "reason": "classified"
    }


# ============================================================
# CONTINUITY / INHERITANCE LOGIC
# ============================================================

def get_family(label):
    return DOCUMENT_FAMILIES.get(label, "unknown")


def apply_inheritance(predictions):
    result = []
    last_valid_label = "unknown"
    last_valid_confidence = 0.0

    for pred in predictions:
        scores = pred.get("scores", {})

        if pred["needs_inheritance"]:
            if last_valid_confidence >= 0.5:
                pred["predicted_label"] = last_valid_label
                pred["confidence"] = last_valid_confidence
                pred["reason"] = f"Inherited ({last_valid_label})"
            else:
                pred["predicted_label"] = "REVIEW_NEEDED"
                pred["reason"] = "Previous page also uncertain"

        elif pred["confidence"] < 0.5 and pred.get("flagged_for_review"):
            if last_valid_confidence >= 0.5:
                pred["predicted_label"] = last_valid_label
                pred["confidence"] = last_valid_confidence
                pred["reason"] = f"Low confidence — inherited ({last_valid_label})"
            else:
                pred["predicted_label"] = "REVIEW_NEEDED"
                pred["reason"] = "Low confidence — previous also uncertain"

        elif len(scores) >= 2:
            sorted_scores = sorted(scores.values(), reverse=True)
            top_score = sorted_scores[0]
            second_score = sorted_scores[1]
            score_gap = top_score - second_score
            current_family = get_family(pred["predicted_label"])
            previous_family = get_family(last_valid_label)

            if (score_gap <= SAME_FAMILY_THRESHOLD and
                    current_family == previous_family and
                    last_valid_label != "unknown" and
                    last_valid_label != pred["predicted_label"]):
                pred["predicted_label"] = last_valid_label
                pred["confidence"] = min(last_valid_confidence * 0.9, 1.0)
                pred["reason"] = f"Position override — scores close"

        if pred["predicted_label"] not in ["REVIEW_NEEDED", "NEEDS_INHERITANCE"]:
            last_valid_label = pred["predicted_label"]
            last_valid_confidence = pred["confidence"]

        result.append(pred)

    return result


# ============================================================
# GROUPING
# ============================================================

def group_pages_into_documents(predictions):
    if not predictions:
        return []

    documents = []
    current_label = predictions[0]["predicted_label"]
    current_pdf = predictions[0]["pdf_name"]
    start_page = predictions[0]["page_number"]
    end_page = predictions[0]["page_number"]
    confidences = [predictions[0]["confidence"]]

    for pred in predictions[1:]:
        same_pdf = pred["pdf_name"] == current_pdf
        same_label = pred["predicted_label"] == current_label

        if same_label and same_pdf:
            end_page = pred["page_number"]
            confidences.append(pred["confidence"])
        else:
            documents.append({
                "pdf_name": current_pdf,
                "document_type": current_label,
                "start_page": start_page,
                "end_page": end_page,
                "page_count": end_page - start_page + 1,
                "avg_confidence": round(
                    sum(confidences) / len(confidences), 3
                )
            })
            current_label = pred["predicted_label"]
            current_pdf = pred["pdf_name"]
            start_page = pred["page_number"]
            end_page = pred["page_number"]
            confidences = [pred["confidence"]]

    documents.append({
        "pdf_name": current_pdf,
        "document_type": current_label,
        "start_page": start_page,
        "end_page": end_page,
        "page_count": end_page - start_page + 1,
        "avg_confidence": round(sum(confidences) / len(confidences), 3)
    })

    return documents


# ============================================================
# DATA LOADING
# ============================================================

def load_ocr_results():
    with open(OCR_RESULTS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_labels():
    df = pd.read_csv(LABELS_FILE)
    df["pdf_name"] = df["pdf_name"].str.strip().str.lower()
    df["label"] = df["label"].str.strip().str.lower()
    df["page_number"] = df["page_number"].astype(int)
    return df


def flatten_ocr_results(ocr_results):
    all_pages = []
    for pdf_name, pages_data in ocr_results.items():
        if isinstance(pages_data, list):
            for page_data in pages_data:
                if isinstance(page_data, dict):
                    page_data["pdf_name"] = pdf_name.lower().strip()
                    all_pages.append(page_data)
        elif isinstance(pages_data, dict):
            pages_data["pdf_name"] = pdf_name.lower().strip()
            all_pages.append(pages_data)

    all_pages.sort(key=lambda x: (x["pdf_name"], x.get("page_number", 0)))
    return all_pages


# ============================================================
# ACCURACY EVALUATION
# ============================================================

def evaluate_accuracy(predictions, labels_df):
    correct = 0
    total = 0
    errors = []
    skipped = 0

    for pred in predictions:
        pdf_name = pred["pdf_name"]
        page_num = pred["page_number"]
        predicted = pred["predicted_label"]

        match = labels_df[
            (labels_df["pdf_name"] == pdf_name) &
            (labels_df["page_number"] == page_num)
        ]

        if len(match) == 0:
            skipped += 1
            continue

        actual = match.iloc[0]["label"]
        total += 1

        if predicted == actual:
            correct += 1
        else:
            errors.append({
                "pdf": pdf_name,
                "page": page_num,
                "predicted": predicted,
                "actual": actual,
                "confidence": pred["confidence"]
            })

    accuracy = (correct / total * 100) if total > 0 else 0

    print(f"\n{'='*60}")
    print(f"ACCURACY REPORT")
    print(f"{'='*60}")
    print(f"Correct    : {correct}")
    print(f"Total      : {total}")
    print(f"Skipped    : {skipped}")
    print(f"Accuracy   : {accuracy:.1f}%")

    if errors:
        print(f"\nMISCLASSIFICATIONS ({len(errors)}):")
        print(f"{'PDF':<10} {'Page':<6} {'Predicted':<30} {'Actual':<30} {'Conf'}")
        print("-" * 85)
        for err in errors:
            print(f"{err['pdf']:<10} {err['page']:<6} "
                  f"{err['predicted']:<30} {err['actual']:<30} "
                  f"{err['confidence']}")

    return {"accuracy": accuracy, "correct": correct,
            "total": total, "errors": errors}


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 60)
    print("Classifier — Approach A")
    print("=" * 60)

    print("\nLoading OCR results...")
    ocr_results = load_ocr_results()

    print("Loading labels...")
    labels_df = load_labels()

    all_pages = flatten_ocr_results(ocr_results)
    print(f"Total pages: {len(all_pages)}")

    print("\nClassifying pages...")
    predictions = []
    for page_data in all_pages:
        pred = predict_page(page_data)
        pred["pdf_name"] = page_data["pdf_name"]
        pred["page_number"] = page_data.get("page_number", 0)
        predictions.append(pred)

    print("Applying continuity logic...")
    predictions = apply_inheritance(predictions)

    print("Grouping into documents...")
    documents = group_pages_into_documents(predictions)

    results = evaluate_accuracy(predictions, labels_df)

    print(f"\n{'='*60}")
    print("DOCUMENT SEGMENTS")
    print(f"{'='*60}")
    for doc in documents:
        pages = (f"Page {doc['start_page']}"
                 if doc['start_page'] == doc['end_page']
                 else f"Pages {doc['start_page']}–{doc['end_page']}")
        print(f"  {doc['pdf_name'].upper()} | {pages} | "
              f"{doc['document_type']} | conf: {doc['avg_confidence']}")

    os.makedirs("outputs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(predictions, f, indent=2)
    with open("outputs/documents.json", "w", encoding="utf-8") as f:
        json.dump(documents, f, indent=2)

    print(f"\nPredictions → {OUTPUT_FILE}")
    print(f"Documents   → outputs/documents.json")

    return predictions, documents, results


if __name__ == "__main__":
    predictions, documents, results = main()
