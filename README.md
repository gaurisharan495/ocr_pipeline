# Document Classification Pipeline — Key Details

---

## What The Pipeline Does

Takes scanned PDFs containing multiple financial documents compiled
together and identifies which pages belong to which document type,
outputting segment boundaries like:
"Tax Invoice: Pages 1–2 | E-Way Bill: Page 3 | Purchase Order: Pages 4–5"

---

## Document Types Classified (12 Categories)

| Label | Document Type |
|---|---|
| tax_invoice | Tax Invoice |
| eway_bill | E-Way Bill |
| purchase_order | Purchase Order |
| qcr_finished_goods | Quality Check Report — Finished Goods |
| goods_receipt_note | Goods Receipt Note (GRN) |
| job_work_order | Job Work Order |
| snag_list_certificate | Snag List Certificate |
| invoice_cash_memo | Invoice / Cash Memo |
| ap_tracker | Accounts Payable Tracker |
| credit_note | Credit Note |
| delivery_challan | Delivery Challan |
| manual_delivery_receipt | Manual Delivery Receipt / Proof of Delivery |

---

## Libraries Used

| Library | Purpose | Local/Online |
|---|---|---|
| paddleocr | OCR — extracts text and bounding boxes from page images | Local after first model download |
| pypdfium2 | Converts PDF pages to images — no Poppler needed | Local |
| numpy | Image array conversion for PaddleOCR | Local |
| scikit-learn | ML utilities | Local |
| fuzzywuzzy | Fuzzy string matching for keyword detection | Local |
| python-Levenshtein | Speed boost for fuzzywuzzy | Local |
| pandas | CSV label loading and evaluation | Local |
| re | Regex pattern matching | Built-in |
| json | Saving/loading OCR results | Built-in |

Zero data sent externally at any stage. All processing on local machine.

---

## Pipeline Architecture

### OCR Pipeline (ocr_pipeline.py)
- Converts each PDF page to a 300 DPI image using pypdfium2
- Runs PaddleOCR on each page image
- Extracts per page:
  - full_text: all words joined and lowercased
  - header_text: first 15 words (title zone)
  - word_count: total words found
  - low_confidence flag: True if fewer than 20 words found
  - text_blocks: list of {text, x, y, width, height, confidence}
    per detected text region — used for layout analysis
  - page_width and page_height in pixels
- Saves everything to outputs/ocr_results.json
- Only needs to run once — results reused by all other scripts

---

### Approach A — Keyword Scoring Classifier (classifier.py)
Accuracy: 84.8% on 34 labeled pages

How it works:
1. Loads OCR results from ocr_results.json
2. For each page, scores it against all 12 document categories
3. Keywords found in header zone (top 15 words) score 3x
4. Keywords found in body text score 1x
5. Negative keywords (rival document words) apply -2 penalty
6. Fuzzy matching handles OCR typos and partial matches
7. Highest scoring category wins
8. Inheritance logic: pages with too few words (<10) inherit
   the label of the previous confidently classified page
9. Position-aware override: if two scores are very close and
   the page is in the same document family as the previous page,
   it inherits the previous label
10. Groups consecutive same-label pages into document segments

Key components:
- KEYWORDS dict: positive keywords per document type
- NEGATIVE_KEYWORDS dict: penalises rival document words
- fuzzy_match_keyword(): handles OCR errors and partial matches
- score_document(): scores a page against all categories
- predict_page(): returns predicted label and confidence
- apply_inheritance(): handles low-word-count continuation pages
- group_pages_into_documents(): merges consecutive same-label pages

---

### Approach B — Boundary Detection + Classifier (boundary_detector.py + pipeline_b.py)

Fundamental difference from Approach A:
Approach A classifies each page independently then groups them.
Approach B finds where documents start and end FIRST, then
classifies each complete segment as one unit using combined text.

Pass 1 — Boundary Detection:
Determines which pages start a new document using three signals
in priority order:

Signal 1 — Document Title in Title Zone (strongest)
  Looks at text in top 20% of page using bounding box coordinates
  Matches against known document title phrases
  Exact phrase match → 0.90 confidence → new document declared
  Only multi-word specific phrases used (no single generic words)

Signal 2 — Definitive Regex Patterns
  Structural identifiers unique to specific document types:
  - GSTIN number (15-char alphanumeric) → Tax Invoice
  - EWB number → E-Way Bill
  - GRN number → Goods Receipt Note
  - Vehicle number pattern → E-Way Bill
  - PO number pattern → Purchase Order
  - JWO number pattern → Job Work Order
  - Challan number pattern → Delivery Challan
  - Column headers (ord qty, recd qty) → AP Tracker
  Pattern found + different type from previous → new document

Signal 3 — Document Reference Number
  Generic document number pattern (INV/, GRN-, PO/, DC/)
  Found in title zone or first 200 chars → likely new document

Decision rules:
  < 10 words → continuation (not enough text to classify)
  Title found → new document (unless same type + no doc number)
  Pattern found + different type → new document
  Doc number found → likely new document
  Nothing found → continuation of previous document

Pass 2 — Segment Classification:
  For each segment found in Pass 1, combines ALL page text
  into one string then classifies using three tiers:
  Tier 1: Definitive regex patterns on combined text
  Tier 2: Trust boundary detector if title confidence >= 0.88
  Tier 3: Keyword presence scoring on combined text
           (presence not count — avoids inflation from long text)
           Header keywords from first page worth 3x

Why combined text is better:
  A 3-page job work order classified as one unit has 3x more
  signal than classifying page 2 alone. OCR errors on one page
  are diluted. Continuation pages contribute their text.

---

## Key Design Decisions

1. No AI/LLMs/APIs — everything runs 100% locally
   Data never leaves the machine at any stage

2. Fuzzy matching (fuzzywuzzy) handles OCR errors
   "challan" matches "delivery challan" at ~85% similarity
   "chalan" matches "challan" at ~85% similarity

3. Header zone gets 3x weight
   Document titles and key identifiers almost always appear
   in the top portion of the page

4. Negative keywords prevent false positives
   "invoice" appearing in an AP Tracker column heading
   no longer causes it to be misclassified as a tax invoice

5. Two separate pipelines preserved
   Approach A: fast, simple, 84.8% accuracy
   Approach B: boundary-first, more robust at scale

---

## File Structure

document_classifier/
├── pdfs/                    ← input PDFs go here
├── outputs/
│   ├── ocr_results.json     ← generated by ocr_pipeline.py
│   ├── predictions.json     ← generated by classifier.py
│   ├── documents.json       ← segment groups from classifier
│   └── segments.json        ← generated by boundary_detector.py
├── data/
│   └── labels.csv           ← manual labels for evaluation
├── ocr_pipeline.py          ← Stage 1: PDF → OCR text + bboxes
├── classifier.py            ← Approach A: page-level classifier
├── boundary_detector.py     ← Approach B: boundary detection
├── pipeline_b.py            ← Approach B: full combined pipeline
└── evaluate_boundary.py     ← boundary detection evaluator

---

## Accuracy Results

| Pipeline | Accuracy |
|---|---|
| Approach A — Keyword Classifier | 84.8% on 34 pages |
| Approach B — Boundary F1 | 90% (Precision 81.8%, Recall 100%) |
| Approach B — Page Accuracy | In progress |

Dataset: 34 labeled pages across 5 PDFs
Document types: 12 categories

---

## How To Run

Step 1 — OCR (run once):
  python ocr_pipeline.py

Step 2 — Approach A Classifier:
  python classifier.py

Step 3 — Approach B Boundary Detector:
  python boundary_detector.py

Step 4 — Evaluate Boundary Detector:
  python evaluate_boundary.py

Step 5 — Full Approach B Pipeline:
  python pipeline_b.py
