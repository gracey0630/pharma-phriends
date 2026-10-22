# Validation report

426 analogs: {'oral': 332, 'sc': 94}. 378 have Medicaid Rx; 1511 NDCs mapped.

## Source freshness (data/raw/*/manifest.csv)
Re-download FDA and CMS files right before any final build (`python -m pipeline.build --refresh`).

| Source | Files | Last pulled |
|---|---|---|
| drugsfda | 1 | 2026-10-22 |
| enrollment | 1 | 2026-10-22 |
| ndc | 2 | 2026-10-22 |
| nme | 1 | 2026-10-22 |
| purple_book | 1 | 2026-10-22 |
| rxclass | 1 | 2026-10-22 |
| sdud | 17 | 2026-10-22 |

## Pool after each rule
Applied in order. Not applied here (flags only): `multi_route` (counts IV forms added later), `label_expansion_in_window` (counts every efficacy supplement), `enrollment_shock_in_window`, and clinic-administered SC products (no flag yet).

| Rule | Analogs left | oral | sc |
|---|---|---|---|
| All analogs (NME / new BLA, approved 2010+, oral or sc) | 426 | 332 | 94 |
| Has a launch quarter (any SDUD row) | 406 | 318 | 88 |
| Launch within 1 year of approval (not `late_launch`) | 387 | 307 | 80 |
| No generic / biosimilar in Q0-Q12 | 387 | 307 | 80 |
| Enough data (>= 12 quarters, no blank quarter after Q2) | 250 | 202 | 48 |

Of those 250: 14 `multi_route`, 137 `label_expansion_in_window`, 227 with an enrollment shock in Q0-Q12.

Launch quarter source: {'first sdud quarter': 406}.

### Peak at the last quarter of data (still climbing) (119)
Among analogs with enough data. Their share_of_peak ends at 1.0 and the fitted m is above 1.
`adbry_sc`, `adempas_oral`, `ajovy_sc`, `amvuttra_sc`, `aptiom_oral`, `austedo_oral`, `besremi_sc`, `biktarvy_oral`, `brilinta_oral`, `brintellix_oral`, `briviact_oral`, `bylvay_oral`, `calquence_oral`, `camzyos_oral`, `caplyta_oral`, `carbaglu_oral`, `cholbam_oral`, `cibinqo_oral`, `corlanor_oral`, `cosentyx_sc`, `diacomit_oral`, `doptelet_oral`, `dupixent_sc`, `edurant_oral`, `eliquis_oral`, `emflaza_oral`, `empaveli_sc`, `enspryng_sc`, `entresto_oral`, `erleada_oral`, `evenity_sc`, `fasenra_sc`, `firazyr_sc`, `fotivda_oral`, `gattex_sc`, `gemtesa_oral`, `gilenya_oral`, `hemlibra_sc`, `horizant_oral`, `ilumya_sc`, `imbruvica_oral`, `imcivree_sc`, `ingrezza_oral`, `inqovi_oral`, `isturisa_oral`, `jakafi_oral`, `jardiance_oral`, `kerendia_oral`, `kevzara_sc`, `latuda_oral`, `lenvima_oral`, `leqvio_sc`, `livmarli_oral`, `lokelma_oral`, `lupkynis_oral`, `lybalvi_oral`, `lynparza_oral`, `mekinist_oral`, `motegrity_oral`, `mounjaro_sc`, `nexletol_oral`, `northera_oral`, `nubeqa_oral`, `nucala_sc`, `nurtecodt_oral`, `nuzyra_oral`, `ofev_oral`, `olumiant_oral`, `onfi_oral`, `opsumit_oral`, `orgovyx_oral`, `orladeyo_oral`, `otezla_oral`, `ozempic_sc`, `palynziq_sc`, `pomalyst_oral`, `praluent_sc`, `prolia_sc`, `pyrukynd_oral`, `qelbree_oral`, `qinlock_oral`, `qulipta_oral`, `reblozyl_sc`, `repatha_sc`, `retevmo_oral`, `rexulti_oral`, `rinvoq_oral`, `rukobia_oral`, `scemblix_oral`, `skytrofa_sc`, `sotyktu_oral`, `strensiq_sc`, `sunosi_oral`, `tafinlar_oral`, `tagrisso_oral`, `takhzyro_sc`, `taltz_sc`, `tavneos_oral`, `tezspire_sc`, `tibsovo_oral`, `tradjenta_oral`, `tremfya_sc`, `trulicity_sc`, `ubrelvy_oral`, `uptravi_oral`, `venclexta_oral`, `verquvo_oral`, `verzenio_oral`, `victoza_sc`, `vonjo_oral`, `voxzogo_sc`, `vraylar_oral`, `wakix_oral`, `welireg_oral`, `xalkori_oral`, `xarelto_oral`, `xcopri_oral`, `zegalogue_sc`, `ztalmy_oral`

### Weak Bass fits (104)
R^2 < 0.9 or a parameter on its bound; 256 analogs fitted.
`accrufer_oral`, `adlyxin_sc`, `akynzeo_oral`, `ampyra_oral`, `amvuttra_sc`, `aptiom_oral`, `baxdela_oral`, `benlysta_sc`, `besremi_sc`, `caprelsa_oral`, `carbaglu_oral`, `cholbam_oral`, `cotellic_oral`, `diacomit_oral`, `doptelet_oral`, `edarbi_oral`, `edurant_oral`, `egrifta_sc`, `ella_oral`, `empaveli_sc`, `epclusa_oral`, `farxiga_oral`, `firazyr_sc`, `fotivda_oral`, `fulyzaq_oral`, `fycompa_oral`, `genvoya_oral`, `gilotrif_oral`, `givlaari_sc`, `harvoni_oral`, `iclusig_oral`, `idhifa_oral`, `imbruvica_oral`, `inlyta_oral`, `inqovi_oral`, `inrebic_oral`, `jakafi_oral`, `kalydeco_oral`, `lenvima_oral`, `lonsurf_oral`, `lorbrena_oral`, `lumakras_oral`, `lynparza_oral`, `mavyret_oral`, `mayzent_oral`, `myalept_sc`, `natazia_oral`, `nerlynx_oral`, `nucala_sc`, `olumiant_oral`, `ongentys_oral`, `orgovyx_oral`, `orkambi_oral`, `osphena_oral`, `oxbryta_oral`, `ozempic_sc`, `pemazyre_oral`, `piqray_oral`, `plegridy_sc`, `pomalyst_oral`, `ponvory_oral`, `potiga_oral`, `pyrukynd_oral`, `qinlock_oral`, `reblozyl_sc`, `retevmo_oral`, `rozlytrek_oral`, `rubraca_oral`, `rydapt_oral`, `savaysa_oral`, `scemblix_oral`, `sivextro_oral`, `solosec_oral`, `stivarga_oral`, `stribild_oral`, `symdeko_oral`, `synribo_sc`, `tabrecta_oral`, `tafinlar_oral`, `taltz_sc`, `talzenna_oral`, `tazverik_oral`, `tibsovo_oral`, `tremfya_sc`, `trikafta_oral`, `tukysa_oral`, `varubi_oral`, `verzenio_oral`, `victoza_sc`, `vitrakvi_oral`, `vonjo_oral`, `vosevi_oral`, `voxzogo_sc`, `xadago_oral`, `xermelo_oral`, `xofluza_oral`, `xospata_oral`, `zegalogue_sc`, `zejula_oral`, `zelboraf_oral`, `zepatier_oral`, `zontivity_oral`, `zydelig_oral`, `zykadia_oral`

## NME brands not in the pool
244 brands from the NME compilation (2010+) have no oral or sc route group.

| Reason | Brands |
|---|---|
| injection, route not stated | 16 |
| no route found | 3 |
| other route | 225 |

Other routes: intravenous 158, topical 17, intramuscular 10, ophthalmic 9, respiratory (inhalation) 7, intravitreal 5, intrathecal 2, ophthalmic; topical 2, nasal 2, inhalation 1, intratracheal 1, intravenous, subcutaneous 1, intravenous; intravesical 1, auricular (otic) 1, intra-articular, intramuscular, intravitreal 1, vaginal 1, intrauterine 1, intraocular; ophthalmic 1, unknown 1, intravenous; subcutaneous 1, intraluminal 1, intravesical 1, intra-arterial; intravenous 1.

### Injection, route not stated (16)
Drugs@FDA lists them only as 'INJECTABLE;INJECTION' (sc, IV or IM?). The original label states the route; not resolved yet, so they're out of the pool.
`aduhelm`, `blincyto`, `brineura`, `cablivi`, `evkeeza`, `imdelltra`, `kanuma`, `lartruvo`, `lumoxiti`, `lymphoseek`, `lynozyfic`, `natpara`, `tanzeum`, `winrevair`, `xiaflex`, `zinbryta`

### No route found (3)
Neither the NDC Directory nor Drugs@FDA Products gives a route.
`belviq`, `erwinaze`, `pepaxto`

### No NDC listings (0)

## Rows to look at

### No Medicaid Rx at all (48)
No SDUD rows for any mapped NDC: often clinic-administered SC products, very recent launches, or NDCs missing from ndc_map.
`aemcolo_oral`, `aphexda_sc`, `bevyxxa_oral`, `brenzavvy_oral`, `daurismo_oral`, `egaten_oral`, `ensacove_oral`, `exdensur_sc`, `fexinidazole_oral`, `forzinity_sc`, `hyrnuo_oral`, `impavido_oral`, `jesduvroq_oral`, `komzifti_oral`, `kybella_sc`, `kygevvi_oral`, `kynamro_sc`, `lampit_oral`, `lerochol_sc`, `lunsumio_sc`, `macrilen_oral`, `moxidectin_oral`, `myqorzo_oral`, `nereus_oral`, `nuzolvence_oral`, `orlynvah_oral`, `ozempic_oral`, `palsonify_oral`, `piasky_sc`, `pizensy_oral`, `qfitlia_sc`, `redemplo_sc`, `rezlidhia_oral`, `ryzneuta_sc`, `saphnelo_sc`, `scenesse_sc`, `seysara_oral`, `spevigo_sc`, `tpoxx_oral`, `truseltiq_oral`, `tryvio_oral`, `ukoniq_oral`, `vizimpro_oral`, `vyleesi_sc`, `xenleta_oral`, `xolremdi_oral`, `xuriden_oral`, `zegfrovy_oral`

### Start marketing date before approval date (3)
Usually an NDC listed shortly before approval; check if more than a few months early.
`farxiga_oral`, `pifeltro_oral`, `seysara_oral`

### Start marketing date > 1 year after approval (15)
Route added later (e.g. an oral form of an injectable), or a delayed launch. Not a first-indication launch curve.
`accrufer_oral`, `actemra_sc`, `benlysta_sc`, `egrifta_sc`, `entyvio_sc`, `granix_sc`, `lunsumio_sc`, `moxidectin_oral`, `ozempic_oral`, `saphnelo_sc`, `sogroya_sc`, `spevigo_sc`, `stendra_oral`, `voqueznatriplepak_oral`, `zegfrovy_oral`

### Fewer than 12 quarters of SDUD data (96)
Fails the 'enough data' rule for analogs.
`aemcolo_oral`, `agamree_oral`, `alhemo_sc`, `alyftrek_oral`, `andembry_sc`, `aphexda_sc`, `aqneursa_oral`, `attruby_oral`, `augtyro_oral`, `avmapkifakzynjacopack_oral`, `bevyxxa_oral`, `bimzelx_sc`, `blujepa_oral`, `brinsupri_oral`, `cobenfy_oral`, `crenessity_oral`, `dawnzera_sc`, `duvyzat_oral`, `ebglyss_sc`, `ekterly_oral`, `elrexfio_sc`, `entyvio_sc`, `exdensur_sc`, `exkivity_oral`, `exxua_oral`, `fabhalta_oral`, `forzinity_sc`, `fruzaqla_oral`, `gomekli_oral`, `hernexeos_oral`, `hympavzi_sc`, `hyrnuo_oral`, `ibtrozi_oral`, `impavido_oral`, `inluriyo_oral`, `inpefa_oral`, `iqirvo_oral`, `itovebi_oral`, `jascayd_oral`, `jesduvroq_oral`, `journavx_oral`, `keytrudaqlex_sc`, `komzifti_oral`, `lazcluze_oral`, `leqselvi_oral`, `litfulo_oral`, `livdelzi_oral`, `lynkuet_oral`, `miplyffa_oral`, `modeyso_oral`, `myqorzo_oral`, `nemluvio_sc`, `ngenla_sc`, `ogsiveo_oral`, `ojemda_oral`, `ojjaara_oral`, `omvoh_sc`, `orlynvah_oral`, `palsonify_oral`, `paxlovid_oral`, `qfitlia_sc`, `redemplo_sc`, `relyvrio_oral`, `revuforj_oral`, `rezdiffra_oral`, `rhapsido_oral`, `rivfloza_sc`, `romvimza_oral`, `rystiggo_sc`, `scenesse_sc`, `sephience_oral`, `skyclarys_oral`, `sogroya_sc`, `sohonos_oral`, `talvey_sc`, `truqap_oral`, `truseltiq_oral`, `tryngolza_sc`, `tryvio_oral`, `ukoniq_oral`, `vafseo_oral`, `vanflyta_oral`, `vanrafia_oral`, `velsipity_oral`, `voqueznatriplepak_oral`, `voranigo_oral`, `voydeya_oral`, `voyxact_sc`, `vyleesi_sc`, `wainua_sc`, `wayrilz_oral`, `xenleta_oral`, `xolremdi_oral`, `yorvipath_sc`, `zilbrysq_sc`, `zurzuvae_oral`

### Suppressed (blank) Rx quarters after launch quarter Q2 (85)
Values stay blank, never 0. Fails the 'no suppressed quarters after Q2' rule.
`actemra_sc`, `addyi_oral`, `adlyxin_sc`, `aemcolo_oral`, `akynzeo_oral`, `alunbrig_oral`, `aphexda_sc`, `ayvakit_oral`, `balversa_oral`, `benznidazole_oral`, `brexafemme_oral`, `brukinsa_oral`, `caprelsa_oral`, `cerdelga_oral`, `cometriq_oral`, `copiktra_oral`, `daklinza_oral`, `daurismo_oral`, `duavee_oral`, `elrexfio_sc`, `esbriet_oral`, `exkivity_oral`, `farydak_oral`, `galafold_oral`, `gavreto_oral`, `imcivree_sc`, `impavido_oral`, `incivek_oral`, `inrebic_oral`, `jesduvroq_oral`, `juxtapid_oral`, `krintafel_oral`, `kybella_sc`, `kynamro_sc`, `lampit_oral`, `lytgobi_oral`, `macrilen_oral`, `mulpleta_oral`, `northera_oral`, `nubeqa_oral`, `odomzo_oral`, `olysio_oral`, `orkambi_oral`, `oxbryta_oral`, `oxlumo_sc`, `potiga_oral`, `prepopik_oral`, `pretomanid_oral`, `qfitlia_sc`, `relyvrio_oral`, `rezlidhia_oral`, `rinvoq_oral`, `rivfloza_sc`, `scenesse_sc`, `signifor_sc`, `siliq_sc`, `sirturo_oral`, `sivextro_oral`, `sohonos_oral`, `sovaldi_oral`, `stendra_oral`, `synribo_sc`, `tegsedi_sc`, `tepmetko_oral`, `trulance_oral`, `truseltiq_oral`, `tryvio_oral`, `ukoniq_oral`, `varubi_oral`, `victrelis_oral`, `vivjoa_oral`, `vizimpro_oral`, `voydeya_oral`, `vyleesi_sc`, `vyndaqel_oral`, `xadago_oral`, `xenleta_oral`, `xermelo_oral`, `xpovio_oral`, `zepatier_oral`, `zokinvy_oral`, `zontivity_oral`, `zurampic_oral`, `zydelig_oral`, `zykadia_oral`

### Generic / biosimilar dispensed within 3 years of first Rx (0)
Out of scope (no generic entry in the first 3 years).

### No ATC class (narrow) (26)
RxClass has no ATC code yet (often recent approvals); fill by hand.
`aemcolo_oral`, `akynzeo_oral`, `avmapkifakzynjacopack_oral`, `brinsupri_oral`, `crenessity_oral`, `cresemba_oral`, `ensacove_oral`, `forzinity_sc`, `gattex_sc`, `ibtrozi_oral`, `inluriyo_oral`, `journavx_oral`, `komzifti_oral`, `modeyso_oral`, `myqorzo_oral`, `nereus_oral`, `nuzolvence_oral`, `paxlovid_oral`, `redemplo_sc`, `tavalisse_oral`, `tryngolza_sc`, `vanrafia_oral`, `veltassa_oral`, `wayrilz_oral`, `xermelo_oral`, `zegfrovy_oral`

### Brands with two route groups (4)
Each route group is its own analog; check which one launched first.
`ozempic_oral`, `ozempic_sc`, `sunlenca_oral`, `sunlenca_sc`

## NDC matching
- application_number: 1096
- application_number; route inferred: 320
- application_number; route from Drugs@FDA: 93
- sdud labeler + name: 2

## Label-read values (data/reference/analog_evidence.csv)
31 values for 8 analogs; 0 approved, 31 waiting for review.

### Analogs with unapproved values (8)
`cosentyx_sc`, `ibrance_oral`, `otezla_oral`, `siliq_sc`, `skyrizi_sc`, `sotyktu_oral`, `taltz_sc`, `tremfya_sc`

### Launch date vs first SDUD Rx quarter differ by > 1 quarter (1)
`ibrance_oral`
