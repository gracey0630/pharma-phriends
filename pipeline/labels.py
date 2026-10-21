"""Original (ORIG) approval labels from Drugs@FDA, for label reads into data/reference/analog_evidence.csv.

ORIG label only: DailyMed is the *current* label and reflects later indications and dosing.
PDFs and extracted text go to data/raw/labels/<ApplNo>.pdf / .txt.

Usage: python -m pipeline.labels 761105 207103   (application numbers; prints the label URL and text path)
"""
import argparse
import csv
import re

from pypdf import PdfReader

from pipeline.common import RAW, download

LABEL_DOC_TYPE = "2"  # ApplicationsDocsType_Lookup: 1 Letter, 2 Label


def orig_label_url(appl_no):
    """URL of the label filed with the application's ORIG approval (earliest, if several)."""
    appl_no = appl_no.zfill(6)
    path = RAW / "drugsfda" / "unzipped" / "ApplicationDocs.txt"
    # read with csv: a few rows have stray tabs that pandas rejects
    with path.open(encoding="latin-1", newline="") as f:
        rows = [r for r in csv.reader(f, delimiter="\t")
                if len(r) >= 8 and r[2] == appl_no and r[3].strip() == "ORIG" and r[1] == LABEL_DOC_TYPE]
    if not rows:
        return ""
    return sorted(rows, key=lambda r: r[-1])[0][-2].replace("http://", "https://")


def label_text(appl_no):
    """Download the ORIG label and return (url, text). Text is cached next to the PDF."""
    url = orig_label_url(appl_no)
    if not url:
        return "", ""
    pdf = download(url, "labels", f"{appl_no.zfill(6)}.pdf")
    txt = pdf.with_suffix(".txt")
    if not txt.exists():
        pages = [p.extract_text() or "" for p in PdfReader(pdf).pages]
        txt.write_text(re.sub(r"[ \t]+", " ", "\n".join(pages)))
    return url, txt.read_text()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("appl_nos", nargs="+")
    for a in ap.parse_args().appl_nos:
        url, _ = label_text(a)
        print(a, url or "no ORIG label in Drugs@FDA", RAW / "labels" / f"{a.zfill(6)}.txt")
