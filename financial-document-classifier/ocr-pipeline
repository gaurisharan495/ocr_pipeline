# ocr_pipeline.py
# Converts PDF pages to images using pypdfium2 (300 DPI)
# Runs PaddleOCR to extract text, bounding boxes, and metadata
# Outputs ocr_results.json to outputs/

# NOTE: This script runs on internal infrastructure only.
# The dataset consists of confidential financial documents
# and cannot be shared publicly.
# Full pipeline available on request for verified recruiters.

# Expected output format per page:
# {
#   "full_text": "...",
#   "header_text": "...",
#   "word_count": 42,
#   "text_blocks": [{"text": "...", "x": 0, "y": 0, ...}],
#   "page_width": 2480,
#   "page_height": 3508
# }
