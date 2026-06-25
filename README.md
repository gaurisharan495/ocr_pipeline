# Financial Document Classification Pipeline

An automated pipeline that classifies scanned PDF pages containing
multiple financial documents into their respective document types.
Runs 100% locally — no data is transmitted externally at any stage.

---

## Accuracy

| Metric | Value |
|---|---|
| **Overall Accuracy** | **91.5%** |
| Total Pages Evaluated | 233 |
| Total PDFs | 29 |
| Document Types | 26 |

### Accuracy By Tier

| Tier | Correct/Total | Accuracy |
|---|---|---|
| Tier 1 — Title Matching | 144/149 | 96.6% |
| Tier 3 — Keyword Scoring | 30/31 | 96.8% |
| Pre-check | 25/25 | 100.0% |
| None (inherited) | 15/29 | 51.7% |

---

## What It Does

Takes scanned PDFs containing multiple financial documents compiled
together and identifies which pages belong to which document type.

**Example Output:**
```
PDF_24 | Pages 1–2 : Tax Invoice
PDF_24 | Page 3    : E-Way Bill
PDF_24 | Pages 4–5 : Purchase Order
PDF_24 | Page 6    : AP Tracker
PDF_24 | Page 7    : Goods Receipt Note
```

---

## Document Types Supported (26 Categories)

| # | Document Type | # | Document Type |
|---|---|---|---|
| 1 | Tax Invoice | 14 | Inspection Checklist |
| 2 | E-Way Bill | 15 | Service Completion Slip |
| 3 | Purchase Order | 16 | Import Receipt |
| 4 | Goods Receipt Note | 17 | Payment Receipt |
| 5 | Credit Note | 18 | Insurance Certificate |
| 6 | Job Work Order | 19 | Bill |
| 7 | Back Page | 20 | Undertaking |
| 8 | AP Tracker | 21 | Consignment Bond |
| 9 | Packing List | 22 | Challan |
| 10 | QCR Finished Goods | 23 | Bill of Lading |
| 11 | Receipt | 24 | Invoice |
| 12 | Manual Delivery Receipt | 25 | Bill of Entry |
| 13 | Commission Working | 26 | Weighbridge Ticket |

---

## Pipeline Architecture

```
SCANNED PDF
      ↓
┌─────────────────────────────────────┐
│         STAGE 1 — OCR               │
│  PaddleOCR extracts per page:       │
│  • Full text (lowercased)           │
│  • Bounding box coordinates         │
│  • Word count                       │
│  • Page dimensions                  │
│  • OCR confidence scores            │
│  Saved to: outputs/ocr_results.json │
└─────────────────────────────────────┘
      ↓
┌─────────────────────────────────────┐
│    STAGE 2 — THREE TIER CLASSIFIER  │
│                                     │
│  PRE-CHECK                          │
│  ├── Terms & Conditions → cont.     │
│  ├── Strong title found → not cont. │
│  └── < 6 words → sparse/back page  │
│                                     │
│  TIER 1 — TITLE MATCHER (Priority)  │
│  ├── Scans top 20% of page          │
│  │   using bounding box y-coords    │
│  ├── Matches 26 document titles     │
│  ├── Longest phrase wins            │
│  │   ("Tax Invoice" beats "Invoice")│
│  └── Negative titles block          │
│       wrong matches                 │
│                                     │
│  TIER 3 — KEYWORD SCORING (Fallback)│
│  ├── Fuzzy keyword matching         │
│  ├── Header zone = 3x weight        │
│  └── Handles generic doc types      │
└─────────────────────────────────────┘
      ↓
┌─────────────────────────────────────┐
│    STAGE 3 — SMART GROUPING         │
│  • Continuation pages inherit       │
│    previous label                   │
│  • Back pages club with previous    │
│  • Consecutive same-label pages     │
│    merged into one segment          │
│  • Segment-level evaluation         │
│    (back page of eway bill counted  │
│     correct when grouped with it)   │
└─────────────────────────────────────┘
      ↓
   FINAL OUTPUT
   Pages X–Y: Document Type
```

---

## Key Design Decisions

### Why Three Tiers?
Different document types are identified in different ways:
- **Group 1** — Have their name written at the top (Tax Invoice, E-Way Bill) → Title matching
- **Group 2** — Generic, identified only by content (Invoice, Bill, Receipt) → Keyword scoring
- **Group 3** — Continuation pages with no unique identity → Inherit from previous

Running tiers in order and stopping at first confident answer
protects reliable signals from being diluted by weaker ones.

### Why Bounding Box Coordinates?
PaddleOCR returns the physical position of every text block on the
page. Using the y-coordinate, we extract only text from the top 20%
of the page — the title zone — for Tier 1 matching. This prevents
body text from interfering with title detection.

### Why Negative Document Titles?
Some pages have multiple document references at the top. For example
a Job Work Order page may reference "Challan No: 45" in its header.
Without negative titles, this would be misclassified as a Challan.
Negative titles block a match if a rival phrase is also present in
the title zone.

### Why Fuzzy Matching?
OCR on scanned documents introduces errors — "challan" may be read
as "chalan", "gstin" as "gst1n". Fuzzy matching with 80% similarity
threshold handles these OCR errors gracefully.

### Smart Evaluation
Back pages and continuation pages are evaluated at segment level.
A back page correctly grouped with its parent document is counted
as correct, reflecting real-world output accuracy honestly.

---

## Tech Stack

| Library | Version | Purpose |
|---|---|---|
| paddleocr | Latest | OCR engine — fully local |
| pypdfium2 | Latest | PDF to image — no Poppler needed |
| numpy | Latest | Image array processing |
| fuzzywuzzy | Latest | Fuzzy string matching |
| python-Levenshtein | Latest | Speed boost for fuzzywuzzy |
| pandas | Latest | Label loading and evaluation |

**Python 3.10+**

All libraries run completely offline after initial installation.
No API calls, no cloud processing, no data transmission.

---

## Project Structure

```
document_classifier/
│
├── ocr_pipeline.py          # Stage 1: PDF → OCR text + bboxes
├── final_pipeline.py        # Stage 2+3: classify + group + output
│
├── outputs/
│   ├── ocr_results.json     # OCR output (auto-generated)
│   ├── final_output.json    # Full classification results
│   └── final_results.txt    # Human readable segment output
│
└── data/
    └── labels.csv           # Manual labels for evaluation
                             # (not included — confidential)
```

---

## Installation

```bash
pip install paddlepaddle
pip install paddleocr
pip install pypdfium2
pip install numpy
pip install fuzzywuzzy python-Levenshtein
pip install pandas
```

> **Note:** PaddleOCR downloads model files on first run only.
> After that it operates fully offline.

---

## Usage

**Step 1 — Place PDFs in a folder named `pdfs/`**

**Step 2 — Run OCR (only needs to run once)**
```bash
python ocr_pipeline.py
```

**Step 3 — Run classifier**
```bash
python final_pipeline.py
```

Results are saved to:
- `outputs/final_results.txt` — human readable output
- `outputs/final_output.json` — full JSON with confidence scores

---

## Adding New Document Types

To support a new document type:

1. Add its title phrases to `DOCUMENT_TITLES` in `final_pipeline.py`:
```python
"new_document_type": ["exact title phrase", "alternative title"]
```

2. Add keywords to `KEYWORDS`:
```python
"new_document_type": ["keyword1", "keyword2", "keyword3"]
```

3. If any other document type gets confused with it,
   add negative titles to `NEGATIVE_DOCUMENT_TITLES`:
```python
"other_type": ["phrase that means it's not other_type"]
```

4. Re-run `final_pipeline.py` — no retraining needed.

---

## Data Confidentiality

This repository contains no dataset, PDF files, OCR outputs,
or label files. All document data is confidential and processed
exclusively on local machines. The pipeline is designed so that
no document content ever leaves the processing environment.

---

## Limitations

- Pages with no title and no strong keywords rely on inheritance
  from the previous page (51.7% accuracy on these pages)
- Handwritten pages may have poor OCR quality
- Heavily degraded scans may reduce OCR confidence
- New document types require manual addition of title phrases

---

## Development Journey

| Stage | Accuracy | Notes |
|---|---|---|
| Approach A — Keyword Scorer | 81.8% | 34 pages, 12 doc types |
| Approach A — Tuned | 84.8% | Refined keywords, fuzzy matching |
| Final Pipeline v1 | 72.1% | Scaled to 233 pages, 26 doc types |
| Final Pipeline v2 | 73.8% | Pre-check improvements |
| Final Pipeline v3 | 85.4% | Smart evaluation, negative titles |
| **Final Pipeline v4** | **91.5%** | **Negative document titles, fixes** |
