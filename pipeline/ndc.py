"""Complete ndc_map with NDCs seen in SDUD but missing from the FDA NDC files.

Rule (docs/data_model.md, Brand -> NDC): application number in the NDC Directory + excluded file
(done in pipeline.fda), plus SDUD NDCs with the same labeler and name. Old packages can drop out of
both FDA files but still have Medicaid claims. An SDUD-only NDC is added when:
  - its labeler code is one of the analog's labelers in ndc_map
  - its SDUD product_name matches the first 10 characters of the brand name (SDUD truncates names)
  - the brand has a single in-scope route group (otherwise the route can't be told from SDUD)
  - it isn't listed in the FDA files under any application (those were routed by pipeline.fda)

Usage: python -m pipeline.ndc   (needs pipeline.fda and pipeline.sdud --pull-only first)
"""
import pandas as pd

from pipeline.common import PROCESSED, ndc9
from pipeline.fda import load_tables
from pipeline.sdud import load_national


def sdud_matches(ndc_map, pool, national, fda_ndc9s):
    seen = national.drop_duplicates("ndc9")[["ndc9", "labeler_code", "product_name"]]
    seen = seen[~seen.ndc9.isin(fda_ndc9s)]
    single_route = pool.groupby("brand_key").analog_id.transform("count") == 1
    rows = []
    for a in pool[single_route].itertuples():
        labelers = set(ndc_map[ndc_map.analog_id == a.analog_id].ndc9.str[:5])
        prefix = a.brand_name.upper()[:10]
        hit = seen[seen.labeler_code.str.zfill(5).isin(labelers)
                   & seen.product_name.str.strip().str.upper().str.startswith(prefix)]
        for r in hit.itertuples():
            rows.append({"analog_id": a.analog_id, "ndc9": r.ndc9, "proprietary_name": r.product_name.strip(),
                         "listing": "sdud only", "match_method": "sdud labeler + name"})
    return pd.DataFrame(rows, columns=ndc_map.columns)


def build(ndc_map, pool, national):
    fda_ndc9s = set(load_tables()["ndc"].PRODUCTNDC.map(ndc9))
    extra = sdud_matches(ndc_map, pool, national, fda_ndc9s)
    out = pd.concat([ndc_map, extra], ignore_index=True).fillna("")
    print(f"ndc_map: {len(ndc_map)} FDA-listed NDCs + {len(extra)} SDUD-only NDCs")
    return out.sort_values(["analog_id", "ndc9"], ignore_index=True)


if __name__ == "__main__":
    pool = pd.read_csv(PROCESSED / "candidate_pool.csv", dtype=str, keep_default_na=False)
    ndc_map = pd.read_csv(PROCESSED / "ndc_map.csv", dtype=str, keep_default_na=False)
    ndc_map = ndc_map[ndc_map.listing != "sdud only"]  # idempotent re-runs
    build(ndc_map, pool, load_national()).to_csv(PROCESSED / "ndc_map.csv", index=False)
