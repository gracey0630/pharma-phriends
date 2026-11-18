"""Original (ORIG) approval labels from Drugs@FDA, for label reads into data/reference/analog_evidence.csv.

ORIG label only: DailyMed is the *current* label and reflects later indications and dosing.
PDFs and extracted text go to data/raw/labels/<ApplNo>.pdf / .txt.

Usage: python -m pipeline.labels 761105 207103   (application numbers; prints the label URL and text path)
       python -m pipeline.labels --check          (is each label quote in analog_evidence.csv in its label?)
"""
import argparse
import csv
import re

import pandas as pd
from pypdf import PdfReader

from pipeline.common import RAW, REFERENCE, download

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
    return url, pdf_text(pdf)


def pdf_text(pdf):
    """Text of a label PDF, cached next to it as .txt."""
    txt = pdf.with_suffix(".txt")
    if not txt.exists():
        pages = [p.extract_text() or "" for p in PdfReader(pdf).pages]
        txt.write_text(re.sub(r"[ \t]+", " ", "\n".join(pages)))
    return txt.read_text()


def _words(s):
    """Lowercase words only, so PDF line breaks, hyphens and punctuation don't break a match."""
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def check_quotes():
    """For each label-sourced row of analog_evidence.csv, is its quote in the label at source_url?

    Returns one row per evidence row: 'verbatim', 'partial: first n of m words' (where it stops matching),
    or 'not checked' (source isn't a label PDF; launch dates and competitor counts need a person).
    """
    path = REFERENCE / "analog_evidence.csv"
    ev = pd.read_csv(path, dtype=str, keep_default_na=False)
    results = []
    for r in ev.itertuples():
        if r.source_type != "ORIG label" or not r.source_url.endswith(".pdf"):
            results.append("not checked")
            continue
        pdf = download(r.source_url, "labels", r.source_url.rsplit("/", 1)[-1])
        text, quote = _words(pdf_text(pdf)), _words(r.quote).split()
        n = 0
        while n < len(quote) and " ".join(quote[:n + 1]) in text:
            n += 1
        results.append("verbatim" if n == len(quote) else f"partial: first {n} of {len(quote)} words")
    ev["quote_check"] = results
    return ev[["analog_id", "field", "value", "approved", "quote_check"]]


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("appl_nos", nargs="*")
    ap.add_argument("--check", action="store_true",
                    help="check every label quote in data/reference/analog_evidence.csv against its label")
    args = ap.parse_args()
    if args.check:
        print(check_quotes().to_string(index=False))
    for a in args.appl_nos:
        url, _ = label_text(a)
        print(a, url or "no ORIG label in Drugs@FDA", RAW / "labels" / f"{a.zfill(6)}.txt")
