import pdfplumber


def parse_pdf(file_path: str) -> list[dict]:
    results = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text()
            if text:
                results.append({"page": i, "text": text.strip(), "total_pages": len(pdf.pages)})
    return results
