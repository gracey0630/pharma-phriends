# Validation report

391 analogs: {'oral': 303, 'sc': 88}. 350 have Medicaid Rx; 1414 NDCs mapped.

## Source freshness (data/raw/*/manifest.csv)
Re-download FDA and CMS files right before any final build (`python -m pipeline.build --refresh`).

| Source | Files | Last pulled |
|---|---|---|
| drugsfda | 1 | 2026-10-21 |
| labels | 8 | 2026-10-21 |
| ndc | 2 | 2026-10-21 |
| nme | 1 | 2026-10-21 |
| purple_book | 1 | 2026-10-21 |
| rxclass | 1 | 2026-10-21 |
| sdud | 17 | 2026-10-21 |

## Rows to look at

### No Medicaid Rx at all (41)
No SDUD rows for any mapped NDC: often clinic-administered SC products, very recent launches, or NDCs missing from ndc_map.
`aphexda_sc`, `brenzavvy_oral`, `daurismo_oral`, `egaten_oral`, `ensacove_oral`, `exdensur_sc`, `fexinidazole_oral`, `forzinity_sc`, `hyrnuo_oral`, `impavido_oral`, `jesduvroq_oral`, `komzifti_oral`, `kybella_sc`, `kygevvi_oral`, `lampit_oral`, `lerochol_sc`, `lunsumio_sc`, `macrilen_oral`, `moxidectin_oral`, `myqorzo_oral`, `nereus_oral`, `nuzolvence_oral`, `orlynvah_oral`, `ozempic_oral`, `palsonify_oral`, `piasky_sc`, `qfitlia_sc`, `redemplo_sc`, `rezlidhia_oral`, `ryzneuta_sc`, `saphnelo_sc`, `scenesse_sc`, `seysara_oral`, `spevigo_sc`, `tpoxx_oral`, `tryvio_oral`, `vizimpro_oral`, `vyleesi_sc`, `xenleta_oral`, `xolremdi_oral`, `xuriden_oral`

### Start marketing date before approval date (3)
Usually an NDC listed shortly before approval; check if more than a few months early.
`farxiga_oral`, `pifeltro_oral`, `seysara_oral`

### Start marketing date > 1 year after approval (16)
Route added later (e.g. an oral form of an injectable), or a delayed launch. Not a first-indication launch curve.
`accrufer_oral`, `actemra_sc`, `benlysta_sc`, `egrifta_sc`, `entyvio_sc`, `esbriet_oral`, `granix_sc`, `lunsumio_sc`, `lynparza_oral`, `moxidectin_oral`, `ozempic_oral`, `saphnelo_sc`, `sogroya_sc`, `spevigo_sc`, `zejula_oral`, `zykadia_oral`

### Fewer than 12 quarters of SDUD data (87)
Fails the 'enough data' rule for analogs.
`agamree_oral`, `alhemo_sc`, `alyftrek_oral`, `andembry_sc`, `aphexda_sc`, `aqneursa_oral`, `attruby_oral`, `augtyro_oral`, `bimzelx_sc`, `blujepa_oral`, `brinsupri_oral`, `cobenfy_oral`, `dawnzera_sc`, `duvyzat_oral`, `ebglyss_sc`, `ekterly_oral`, `elrexfio_sc`, `entyvio_sc`, `exdensur_sc`, `exxua_oral`, `fabhalta_oral`, `forzinity_sc`, `fruzaqla_oral`, `gomekli_oral`, `hernexeos_oral`, `hympavzi_sc`, `hyrnuo_oral`, `ibtrozi_oral`, `impavido_oral`, `inluriyo_oral`, `inpefa_oral`, `iqirvo_oral`, `itovebi_oral`, `jascayd_oral`, `jesduvroq_oral`, `journavx_oral`, `keytrudaqlex_sc`, `komzifti_oral`, `lazcluze_oral`, `leqselvi_oral`, `litfulo_oral`, `livdelzi_oral`, `lynkuet_oral`, `miplyffa_oral`, `modeyso_oral`, `myqorzo_oral`, `nemluvio_sc`, `ngenla_sc`, `ogsiveo_oral`, `ojemda_oral`, `ojjaara_oral`, `omvoh_sc`, `orlynvah_oral`, `palsonify_oral`, `qfitlia_sc`, `redemplo_sc`, `revuforj_oral`, `rezdiffra_oral`, `rhapsido_oral`, `rivfloza_sc`, `romvimza_oral`, `rystiggo_sc`, `scenesse_sc`, `sephience_oral`, `skyclarys_oral`, `sogroya_sc`, `sohonos_oral`, `talvey_sc`, `truqap_oral`, `tryngolza_sc`, `tryvio_oral`, `vafseo_oral`, `vanflyta_oral`, `vanrafia_oral`, `velsipity_oral`, `voranigo_oral`, `voydeya_oral`, `voyxact_sc`, `vyleesi_sc`, `wainua_sc`, `wayrilz_oral`, `xenleta_oral`, `xolremdi_oral`, `yorvipath_sc`, `zejula_oral`, `zilbrysq_sc`, `zurzuvae_oral`

### Suppressed (blank) Rx quarters after launch quarter Q2 (65)
Values stay blank, never 0. Fails the 'no suppressed quarters after Q2' rule.
`actemra_sc`, `addyi_oral`, `akynzeo_oral`, `alunbrig_oral`, `aphexda_sc`, `ayvakit_oral`, `balversa_oral`, `benznidazole_oral`, `brukinsa_oral`, `caprelsa_oral`, `cerdelga_oral`, `cometriq_oral`, `copiktra_oral`, `daurismo_oral`, `duavee_oral`, `elrexfio_sc`, `esbriet_oral`, `galafold_oral`, `gavreto_oral`, `imcivree_sc`, `impavido_oral`, `inrebic_oral`, `jesduvroq_oral`, `juxtapid_oral`, `krintafel_oral`, `kybella_sc`, `lampit_oral`, `lytgobi_oral`, `macrilen_oral`, `mulpleta_oral`, `northera_oral`, `nubeqa_oral`, `odomzo_oral`, `orkambi_oral`, `oxbryta_oral`, `oxlumo_sc`, `pretomanid_oral`, `qfitlia_sc`, `rezlidhia_oral`, `rinvoq_oral`, `rivfloza_sc`, `scenesse_sc`, `signifor_sc`, `siliq_sc`, `sirturo_oral`, `sivextro_oral`, `sohonos_oral`, `sovaldi_oral`, `tepmetko_oral`, `trulance_oral`, `tryvio_oral`, `varubi_oral`, `vivjoa_oral`, `vizimpro_oral`, `voydeya_oral`, `vyleesi_sc`, `vyndaqel_oral`, `xadago_oral`, `xenleta_oral`, `xermelo_oral`, `xpovio_oral`, `zepatier_oral`, `zokinvy_oral`, `zydelig_oral`, `zykadia_oral`

### Generic / biosimilar dispensed within 3 years of first Rx (0)
Out of scope (no generic entry in the first 3 years).

### No ATC class (narrow) (21)
RxClass has no ATC code yet (often recent approvals); fill by hand.
`akynzeo_oral`, `brinsupri_oral`, `cresemba_oral`, `ensacove_oral`, `forzinity_sc`, `gattex_sc`, `ibtrozi_oral`, `inluriyo_oral`, `journavx_oral`, `komzifti_oral`, `modeyso_oral`, `myqorzo_oral`, `nereus_oral`, `nuzolvence_oral`, `redemplo_sc`, `tavalisse_oral`, `tryngolza_sc`, `vanrafia_oral`, `veltassa_oral`, `wayrilz_oral`, `xermelo_oral`

### Brands with two route groups (2)
Each route group is its own analog; check which one launched first.
`ozempic_oral`, `ozempic_sc`

## NDC matching
- application_number: 1092
- application_number; route inferred: 320
- sdud labeler + name: 2

## Label-read values (data/reference/analog_evidence.csv)
31 values for 8 analogs; 0 approved, 31 waiting for review.

### Analogs with unapproved values (8)
`cosentyx_sc`, `ibrance_oral`, `otezla_oral`, `siliq_sc`, `skyrizi_sc`, `sotyktu_oral`, `taltz_sc`, `tremfya_sc`

### Launch date vs first SDUD Rx quarter differ by > 1 quarter (1)
`ibrance_oral`
