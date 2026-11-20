"""Checks on what the Label Research Agent extracts: is a quote really on its source page, and are proposed
competitors real, approved before the analog's launch, and still without generics.

Spec: analog_finder/docs/components/extract.md
"""
import csv
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd

from pipeline.common import RAW
from pipeline.labels import pdf_text

DRUGSFDA = RAW / "drugsfda" / "unzipped"


# --- quotes -------------------------------------------------------------------------------------------------

def _words(text):
    """Lowercase words only (PR #6's rule): punctuation, line breaks and spacing don't affect a match."""
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _dehyphenate(text):
    """Join a word a PDF split with a hyphen at a line break: 'antipsy-\\nchotic' -> 'antipsychotic'."""
    return re.sub(r"(\w)-[ \t]*\r?\n[ \t]*(\w)", r"\1\2", str(text))


def _matched(quote_words, text_words):
    """How many of the quote's words, from the start, appear in order as one run in the text."""
    padded = f" {text_words} "
    n = 0
    while n < len(quote_words) and f" {' '.join(quote_words[:n + 1])} " in padded:
        n += 1
    return n


def quote_check(quote, text):
    """('verbatim', '') if every word of the quote appears in order in the text, else
    ('partial', 'first n of m words match').

    The text is tried as is and with line-break hyphens joined, since a hyphen at a line break can be part of the
    word ('once-daily') or only a break ('antipsy-chotic'). Last, letters and digits are compared with every space
    removed, because PDF text extraction can split a word ('sc hizophrenia' in Latuda's label): same characters in
    the same order, so still verbatim."""
    q = _words(quote).split()
    if not q:
        return "partial", "empty quote"
    best = max(_matched(q, _words(t)) for t in (text, _dehyphenate(text)))
    if best == len(q):
        return "verbatim", ""
    if "".join(q) in _words(_dehyphenate(text)).replace(" ", "") or "".join(q) in _words(text).replace(" ", ""):
        return "verbatim", ""
    return "partial", f"first {best} of {len(q)} words match the source"


# --- page text ----------------------------------------------------------------------------------------------

class _Text(HTMLParser):
    BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "td"}
    SKIP = {"script", "style"}

    def __init__(self):
        super().__init__()
        self.parts, self._skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self._skip = max(0, self._skip - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)


def html_text(html):
    p = _Text()
    p.feed(html)
    text = "".join(p.parts).replace("\xa0", " ")
    return re.sub(r"\n\s*\n+", "\n", re.sub(r"[ \t]+", " ", text)).strip()


def page_text(path):
    """Plain text of a fetched file: PDF (text cached next to it), HTML or plain text."""
    path = Path(path)
    if path.suffix == ".pdf":
        return pdf_text(path)
    raw = path.read_bytes().decode("utf-8", errors="replace")
    if path.suffix in (".html", ".htm", ".xml") or raw.lstrip()[:1] == "<":
        return html_text(raw)
    return raw


# --- Drugs@FDA ----------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Approval:
    brand: str
    appl_no: str
    appl_type: str        # NDA / BLA
    ingredient: str
    approval_date: str    # YYYY-MM-DD of the ORIG approval


def _rows(name):
    # csv, not pandas: a few Drugs@FDA rows have stray tabs (pipeline/labels.py)
    with (DRUGSFDA / name).open(encoding="latin-1", newline="") as f:
        r = csv.reader(f, delimiter="\t")
        header = next(r)
        for row in r:
            yield dict(zip(header, row))


class DrugsFDA:
    """Lookups in the pipeline's Drugs@FDA files (data/raw/drugsfda/unzipped)."""

    def __init__(self):
        self.appl_type = {r["ApplNo"]: r["ApplType"].strip() for r in _rows("Applications.txt")}
        self.orig_ap = {}
        for r in _rows("Submissions.txt"):
            if r["SubmissionType"].strip() == "ORIG" and r["SubmissionStatus"].strip() == "AP":
                d = r["SubmissionStatusDate"][:10]
                if r["ApplNo"] not in self.orig_ap or d < self.orig_ap[r["ApplNo"]]:
                    self.orig_ap[r["ApplNo"]] = d
        self.by_brand, self.by_ingredient = {}, {}
        for r in _rows("Products.txt"):
            appl, brand, ingr = r["ApplNo"], r["DrugName"].strip().upper(), r["ActiveIngredient"].strip().upper()
            self.by_brand.setdefault(brand, set()).add(appl)
            self.by_ingredient.setdefault(ingr, set()).add(appl)
        self._ingredient_of = {}
        for ingr, appls in self.by_ingredient.items():
            for a in appls:
                self._ingredient_of.setdefault(a, ingr)

    def brand_approval(self, brand):
        """The earliest ORIG approval among the NDA / BLA applications sold under this brand name, or None."""
        found = [Approval(brand.upper(), a, self.appl_type.get(a, ""), self._ingredient_of.get(a, ""),
                          self.orig_ap[a])
                 for a in self.by_brand.get(brand.strip().upper(), ())
                 if self.appl_type.get(a) in ("NDA", "BLA") and a in self.orig_ap]
        return min(found, key=lambda x: x.approval_date) if found else None

    def first_anda(self, ingredient):
        """Date of the earliest approved ANDA for this active ingredient (exact Drugs@FDA spelling), or None."""
        dates = [self.orig_ap[a] for a in self.by_ingredient.get(ingredient.strip().upper(), ())
                 if self.appl_type.get(a) == "ANDA" and a in self.orig_ap]
        return min(dates) if dates else None


class GenericEntry:
    """When a brand's generic entered the market.

    For a brand in our pool: the first SDUD quarter a generic was dispensed (analogs.csv `generic / exclusivity
    date`; blank = none yet), which is actual entry. Otherwise (brands approved before 2010): the first ANDA
    approval, a proxy, since a settlement or patent can delay the launch for years (Latuda: ANDA 2019, generic
    dispensed 2023)."""

    def __init__(self, analogs, fda):
        self.fda = fda
        self.sdud = {}
        for brand, q in zip(analogs["brand name"], analogs["generic / exclusivity date"]):
            self.sdud.setdefault(str(brand).strip().upper(), "" if pd.isna(q) else str(q).strip())

    def __call__(self, approval):
        """(YYYY-MM-DD or None, source) for an Approval."""
        if approval.brand in self.sdud:
            q = self.sdud[approval.brand]
            if len(q) == 6 and q[4] == "Q":
                return f"{q[:4]}-{(int(q[-1]) - 1) * 3 + 1:02d}-01", "first generic dispensed (SDUD)"
            return None, "no generic dispensed (SDUD)"
        return self.fda.first_anda(approval.ingredient), "first ANDA approval (proxy)"


def check_competitors(proposed, launch_date, fda, generic_entry=None):
    """Split the model's proposed competitors into (kept, dropped).

    proposed: dicts with at least `brand`. launch_date: 'YYYY-MM-DD' (or 'YYYY-MM', read as the 1st).
    kept: Approval for each brand found in Drugs@FDA, approved before the launch, with no generic entry before it
    (generic_entry: a GenericEntry; default the first ANDA approval). dropped: (brand, reason). A brand proposed
    twice counts once."""
    generic_entry = generic_entry or (lambda a: (fda.first_anda(a.ingredient), "first ANDA approval (proxy)"))
    launch = launch_date if len(launch_date) == 10 else f"{launch_date[:7]}-01"
    kept, dropped, seen = [], [], set()
    for p in proposed:
        brand = str(p.get("brand", "")).strip()
        if not brand or brand.upper() in seen:
            continue
        seen.add(brand.upper())
        a = fda.brand_approval(brand)
        if a is None:
            dropped.append((brand, "not found as an NDA / BLA brand in Drugs@FDA"))
        elif a.approval_date >= launch:
            dropped.append((brand, f"approved {a.approval_date}, not before the launch ({launch})"))
        elif (g := generic_entry(a))[0] and g[0] < launch:
            dropped.append((brand, f"generic entry {g[0]} ({g[1]}), before the launch"))
        else:
            kept.append(a)
    return sorted(kept, key=lambda a: (a.approval_date, a.brand)), dropped
