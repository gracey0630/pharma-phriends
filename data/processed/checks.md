# Validation report

426 analogs: {'oral': 332, 'sc': 94}. 406 have Medicaid Rx (28 of them only in suppressed rows); 1513 NDCs mapped.

TRx = reported rows + 5 per suppressed row (low 1, high 10; `trx_low` / `trx_high`). A quarter with no SDUD row is 0 TRx. Medicaid TRx to date: 172,586,622, of which 61,115 imputed.

## Source freshness (data/raw/*/manifest.csv)
Re-download FDA and CMS files right before any final build (`python -m pipeline.build --refresh`).

| Source | Files | Last pulled |
|---|---|---|
| drugsfda | 1 | 2026-10-30 |
| enrollment | 1 | 2026-10-30 |
| ndc | 2 | 2026-10-30 |
| nme | 1 | 2026-10-30 |
| purple_book | 1 | 2026-10-30 |
| rxclass | 1 | 2026-11-17 |
| sdud | 17 | 2026-10-31 |

## Pool after each rule
Applied in order. Not applied here (flags only): `low_volume`, `multi_route` (counts IV forms added later), `label_expansion_in_window` (counts every efficacy supplement), `enrollment_shock_in_window`, and clinic-administered SC products (no flag yet).

| Rule | Analogs left | oral | sc |
|---|---|---|---|
| All analogs (NME / new BLA, approved 2010+, oral or sc) | 426 | 332 | 94 |
| Has a launch quarter (any SDUD row) | 406 | 318 | 88 |
| Launch within 1 year of approval (not `late_launch`) | 387 | 307 | 80 |
| No generic / biosimilar in Q0-Q12 | 387 | 307 | 80 |
| Enough data (>= 12 quarters, <= 20% of Q3-Q20 TRx imputed) | 261 | 213 | 48 |

Of those 261: 50 `low_volume` (peak < 300 TRx a quarter), 14 `multi_route`, 145 `label_expansion_in_window`, 237 with an enrollment shock in Q0-Q12.

Launch quarter source: {'first sdud quarter': 403, 'evidence': 3}.

Peak for share_of_peak = Q0-Q28: 164 of 261 have the full window (`peak_confirmed`); for the other 97 it's the peak so far, so their share_of_peak is an upper bound.

### Peak not confirmed (less than the full Q0-Q28 window) (97)
Among analogs with enough data. Use their shape (p, q); show share of peak as '<= X'.
`adbry_sc`, `amvuttra_sc`, `azstarys_oral`, `besremi_sc`, `brexafemme_oral`, `brukinsa_oral`, `bylvay_oral`, `camzyos_oral`, `caplyta_oral`, `cibinqo_oral`, `dayvigo_oral`, `diacomit_oral`, `dojolvi_oral`, `emgality_sc`, `empaveli_sc`, `enspryng_sc`, `epidiolex_oral`, `evenity_sc`, `evrysdi_oral`, `exkivity_oral`, `firdapse_oral`, `fotivda_oral`, `galafold_oral`, `gemtesa_oral`, `givlaari_sc`, `ilumya_sc`, `imcivree_sc`, `inqovi_oral`, `inrebic_oral`, `isturisa_oral`, `kerendia_oral`, `koselugo_oral`, `leqvio_sc`, `livmarli_oral`, `livtencity_oral`, `lokelma_oral`, `lorbrena_oral`, `lumakras_oral`, `lupkynis_oral`, `lybalvi_oral`, `mayzent_oral`, `motegrity_oral`, `mounjaro_sc`, `nexletol_oral`, `nextstellis_oral`, `nourianz_oral`, `nubeqa_oral`, `nurtecodt_oral`, `nuzyra_oral`, `ongentys_oral`, `orgovyx_oral`, `orladeyo_oral`, `oxbryta_oral`, `pemazyre_oral`, `pifeltro_oral`, `piqray_oral`, `ponvory_oral`, `pretomanid_oral`, `qelbree_oral`, `qinlock_oral`, `qulipta_oral`, `quviviq_oral`, `reblozyl_sc`, `relyvrio_oral`, `retevmo_oral`, `reyvow_oral`, `rezurock_oral`, `rinvoq_oral`, `rolvedon_sc`, `rozlytrek_oral`, `rukobia_oral`, `scemblix_oral`, `skyrizi_sc`, `skytrofa_sc`, `sotyktu_oral`, `sunosi_oral`, `tabrecta_oral`, `talzenna_oral`, `tavneos_oral`, `tazverik_oral`, `tezspire_sc`, `trikafta_oral`, `tukysa_oral`, `turalio_oral`, `ubrelvy_oral`, `verquvo_oral`, `vitrakvi_oral`, `vonjo_oral`, `voxzogo_sc`, `wakix_oral`, `welireg_oral`, `xcopri_oral`, `xofluza_oral`, `xospata_oral`, `zegalogue_sc`, `zeposia_oral`, `ztalmy_oral`

### Peak at the last quarter of the peak window (still climbing) (105)
Among analogs with enough data: the highest quarter is Q28, or the latest complete quarter for analogs without the full window.
`adbry_sc`, `adempas_oral`, `ajovy_sc`, `alecensa_oral`, `amvuttra_sc`, `besremi_sc`, `bosulif_oral`, `braftovi_oral`, `brilinta_oral`, `briviact_oral`, `brukinsa_oral`, `bylvay_oral`, `camzyos_oral`, `caplyta_oral`, `cholbam_oral`, `cibinqo_oral`, `cotellic_oral`, `cresemba_oral`, `diacomit_oral`, `dificid_oral`, `doptelet_oral`, `dupixent_sc`, `eliquis_oral`, `empaveli_sc`, `enspryng_sc`, `entresto_oral`, `evenity_sc`, `farxiga_oral`, `firdapse_oral`, `fotivda_oral`, `gattex_sc`, `gemtesa_oral`, `iclusig_oral`, `imbruvica_oral`, `imcivree_sc`, `inqovi_oral`, `isturisa_oral`, `jakafi_oral`, `jardiance_oral`, `kalydeco_oral`, `kerendia_oral`, `kisqali_oral`, `lenvima_oral`, `leqvio_sc`, `linzess_oral`, `livmarli_oral`, `lokelma_oral`, `lorbrena_oral`, `lupkynis_oral`, `lybalvi_oral`, `mekinist_oral`, `mektovi_oral`, `mounjaro_sc`, `myalept_sc`, `myrbetriq_oral`, `nesina_oral`, `nexletol_oral`, `nubeqa_oral`, `nurtecodt_oral`, `nuzyra_oral`, `olumiant_oral`, `orgovyx_oral`, `orladeyo_oral`, `otezla_oral`, `palynziq_sc`, `praluent_sc`, `prevymis_oral`, `qelbree_oral`, `qinlock_oral`, `qulipta_oral`, `repatha_sc`, `retevmo_oral`, `rexulti_oral`, `rinvoq_oral`, `rukobia_oral`, `scemblix_oral`, `skyrizi_sc`, `skytrofa_sc`, `sotyktu_oral`, `sunosi_oral`, `tafinlar_oral`, `takhzyro_sc`, `taltz_sc`, `tavneos_oral`, `tezspire_sc`, `tremfya_sc`, `trulance_oral`, `trulicity_sc`, `tymlos_sc`, `ubrelvy_oral`, `uptravi_oral`, `venclexta_oral`, `verquvo_oral`, `victoza_sc`, `vonjo_oral`, `voxzogo_sc`, `wakix_oral`, `welireg_oral`, `xarelto_oral`, `xcopri_oral`, `xeljanz_oral`, `xtandi_oral`, `zegalogue_sc`, `ztalmy_oral`, `zytiga_oral`

### Weak Bass fits (106)
R^2 < 0.9 or a parameter on its bound; 268 analogs fitted, 38 of the weak fits are `low_volume`.
`accrufer_oral`, `adlyxin_sc`, `akynzeo_oral`, `ampyra_oral`, `amvuttra_sc`, `aptiom_oral`, `baxdela_oral`, `benlysta_sc`, `besremi_sc`, `brexafemme_oral`, `cholbam_oral`, `cotellic_oral`, `daklinza_oral`, `diacomit_oral`, `doptelet_oral`, `edarbi_oral`, `edurant_oral`, `egrifta_sc`, `ella_oral`, `empaveli_sc`, `epclusa_oral`, `exkivity_oral`, `firazyr_sc`, `fotivda_oral`, `fulyzaq_oral`, `fycompa_oral`, `galafold_oral`, `genvoya_oral`, `givlaari_sc`, `harvoni_oral`, `iclusig_oral`, `idhifa_oral`, `imbruvica_oral`, `incivek_oral`, `inlyta_oral`, `inqovi_oral`, `inrebic_oral`, `jakafi_oral`, `kalydeco_oral`, `lenvima_oral`, `lonsurf_oral`, `lorbrena_oral`, `lumakras_oral`, `lynparza_oral`, `mavyret_oral`, `mayzent_oral`, `natazia_oral`, `nerlynx_oral`, `nucala_sc`, `olumiant_oral`, `olysio_oral`, `ongentys_oral`, `orgovyx_oral`, `orkambi_oral`, `osphena_oral`, `oxbryta_oral`, `ozempic_sc`, `pemazyre_oral`, `piqray_oral`, `plegridy_sc`, `ponvory_oral`, `potiga_oral`, `pretomanid_oral`, `qinlock_oral`, `reblozyl_sc`, `relyvrio_oral`, `retevmo_oral`, `rubraca_oral`, `rydapt_oral`, `savaysa_oral`, `scemblix_oral`, `sivextro_oral`, `solosec_oral`, `sovaldi_oral`, `stivarga_oral`, `stribild_oral`, `symdeko_oral`, `synribo_sc`, `tabrecta_oral`, `taltz_sc`, `talzenna_oral`, `tazverik_oral`, `tibsovo_oral`, `tremfya_sc`, `trikafta_oral`, `tukysa_oral`, `varubi_oral`, `verzenio_oral`, `victoza_sc`, `victrelis_oral`, `viekirapak_oral`, `vitrakvi_oral`, `vonjo_oral`, `vosevi_oral`, `voxzogo_sc`, `xadago_oral`, `xermelo_oral`, `xofluza_oral`, `zegalogue_sc`, `zejula_oral`, `zelboraf_oral`, `zepatier_oral`, `zontivity_oral`, `zurampic_oral`, `zydelig_oral`, `zykadia_oral`

### Low Medicaid volume (50)
Among analogs with enough data: peak < 300 TRx a quarter (mid estimate). Counting noise alone gives weak Bass fits at this size, so show the flag next to the fit.
`akynzeo_oral`, `amvuttra_sc`, `baxdela_oral`, `besremi_sc`, `bylvay_oral`, `cerdelga_oral`, `cholbam_oral`, `cotellic_oral`, `empaveli_sc`, `enspryng_sc`, `exkivity_oral`, `firdapse_oral`, `fotivda_oral`, `fulyzaq_oral`, `galafold_oral`, `gattex_sc`, `givlaari_sc`, `hetlioz_oral`, `idhifa_oral`, `inqovi_oral`, `inrebic_oral`, `isturisa_oral`, `livtencity_oral`, `myalept_sc`, `nourianz_oral`, `odomzo_oral`, `ongentys_oral`, `pemazyre_oral`, `ponvory_oral`, `pretomanid_oral`, `qinlock_oral`, `relyvrio_oral`, `retevmo_oral`, `rozlytrek_oral`, `rubraca_oral`, `rydapt_oral`, `sivextro_oral`, `synribo_sc`, `tabrecta_oral`, `talzenna_oral`, `tazverik_oral`, `tibsovo_oral`, `turalio_oral`, `vitrakvi_oral`, `vonjo_oral`, `xadago_oral`, `xermelo_oral`, `zurampic_oral`, `zydelig_oral`, `zykadia_oral`

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

### No Medicaid Rx at all (20)
No SDUD rows for any mapped NDC: often clinic-administered SC products, very recent launches, or NDCs missing from ndc_map.
`brenzavvy_oral`, `egaten_oral`, `ensacove_oral`, `fexinidazole_oral`, `kygevvi_oral`, `lerochol_sc`, `lunsumio_sc`, `moxidectin_oral`, `nereus_oral`, `nuzolvence_oral`, `ozempic_oral`, `piasky_sc`, `pizensy_oral`, `ryzneuta_sc`, `saphnelo_sc`, `seysara_oral`, `spevigo_sc`, `tpoxx_oral`, `xuriden_oral`, `zegfrovy_oral`

### Medicaid Rx only in suppressed rows (28)
Every SDUD row is suppressed (< 11 Rx), so all their TRx is imputed.
`aemcolo_oral`, `aphexda_sc`, `bevyxxa_oral`, `daurismo_oral`, `exdensur_sc`, `forzinity_sc`, `hyrnuo_oral`, `impavido_oral`, `jesduvroq_oral`, `komzifti_oral`, `kybella_sc`, `kynamro_sc`, `lampit_oral`, `macrilen_oral`, `myqorzo_oral`, `orlynvah_oral`, `palsonify_oral`, `qfitlia_sc`, `redemplo_sc`, `rezlidhia_oral`, `scenesse_sc`, `truseltiq_oral`, `tryvio_oral`, `ukoniq_oral`, `vizimpro_oral`, `vyleesi_sc`, `xenleta_oral`, `xolremdi_oral`

### Start marketing date before approval date (3)
Usually an NDC listed shortly before approval; check if more than a few months early.
`farxiga_oral`, `pifeltro_oral`, `seysara_oral`

### Start marketing date > 1 year after approval (15)
Route added later (e.g. an oral form of an injectable), or a delayed launch. Not a first-indication launch curve.
`accrufer_oral`, `actemra_sc`, `benlysta_sc`, `egrifta_sc`, `entyvio_sc`, `granix_sc`, `lunsumio_sc`, `moxidectin_oral`, `ozempic_oral`, `saphnelo_sc`, `sogroya_sc`, `spevigo_sc`, `stendra_oral`, `voqueznatriplepak_oral`, `zegfrovy_oral`

### Fewer than 12 quarters of SDUD data (96)
Fails the 'enough data' rule for analogs.
`aemcolo_oral`, `agamree_oral`, `alhemo_sc`, `alyftrek_oral`, `andembry_sc`, `aphexda_sc`, `aqneursa_oral`, `attruby_oral`, `augtyro_oral`, `avmapkifakzynjacopack_oral`, `bevyxxa_oral`, `bimzelx_sc`, `blujepa_oral`, `brinsupri_oral`, `cobenfy_oral`, `crenessity_oral`, `dawnzera_sc`, `duvyzat_oral`, `ebglyss_sc`, `ekterly_oral`, `elrexfio_sc`, `entyvio_sc`, `exdensur_sc`, `exkivity_oral`, `exxua_oral`, `fabhalta_oral`, `forzinity_sc`, `fruzaqla_oral`, `gomekli_oral`, `hernexeos_oral`, `hympavzi_sc`, `hyrnuo_oral`, `ibtrozi_oral`, `impavido_oral`, `inluriyo_oral`, `inpefa_oral`, `iqirvo_oral`, `itovebi_oral`, `jascayd_oral`, `jesduvroq_oral`, `journavx_oral`, `keytrudaqlex_sc`, `komzifti_oral`, `lazcluze_oral`, `leqselvi_oral`, `litfulo_oral`, `livdelzi_oral`, `lynkuet_oral`, `miplyffa_oral`, `modeyso_oral`, `myqorzo_oral`, `nemluvio_sc`, `ngenla_sc`, `ogsiveo_oral`, `ojemda_oral`, `ojjaara_oral`, `omvoh_sc`, `orlynvah_oral`, `palsonify_oral`, `paxlovid_oral`, `qfitlia_sc`, `redemplo_sc`, `relyvrio_oral`, `revuforj_oral`, `rezdiffra_oral`, `rhapsido_oral`, `rivfloza_sc`, `romvimza_oral`, `rystiggo_sc`, `scenesse_sc`, `sephience_oral`, `skyclarys_oral`, `sogroya_sc`, `sohonos_oral`, `talvey_sc`, `truqap_oral`, `truseltiq_oral`, `tryngolza_sc`, `tryvio_oral`, `ukoniq_oral`, `vafseo_oral`, `vanflyta_oral`, `vanrafia_oral`, `velsipity_oral`, `voqueznatriplepak_oral`, `voranigo_oral`, `voydeya_oral`, `voyxact_sc`, `vyleesi_sc`, `wainua_sc`, `wayrilz_oral`, `xenleta_oral`, `xolremdi_oral`, `yorvipath_sc`, `zilbrysq_sc`, `zurzuvae_oral`

### More than 20% of Q3-Q20 TRx imputed (37)
Fails the 'enough data' rule: the curve would be mostly imputed suppressed rows.
`addyi_oral`, `aemcolo_oral`, `alunbrig_oral`, `ayvakit_oral`, `balversa_oral`, `benznidazole_oral`, `caprelsa_oral`, `carbaglu_oral`, `cometriq_oral`, `copiktra_oral`, `daurismo_oral`, `farydak_oral`, `gavreto_oral`, `impavido_oral`, `juxtapid_oral`, `krintafel_oral`, `kybella_sc`, `kynamro_sc`, `lampit_oral`, `macrilen_oral`, `mulpleta_oral`, `oxlumo_sc`, `pyrukynd_oral`, `signifor_sc`, `sirturo_oral`, `stendra_oral`, `tegsedi_sc`, `tepmetko_oral`, `truseltiq_oral`, `ukoniq_oral`, `vivjoa_oral`, `vizimpro_oral`, `vyleesi_sc`, `vyndaqel_oral`, `xenleta_oral`, `xpovio_oral`, `zokinvy_oral`

### Enough-data status depends on the imputation (25)
Pass the 20% cap at 1 Rx per suppressed row but not at 10; the rule uses 5.
`addyi_oral`, `alunbrig_oral`, `ayvakit_oral`, `caprelsa_oral`, `carbaglu_oral`, `cometriq_oral`, `copiktra_oral`, `exkivity_oral`, `fotivda_oral`, `gavreto_oral`, `idhifa_oral`, `inrebic_oral`, `juxtapid_oral`, `mulpleta_oral`, `odomzo_oral`, `oxlumo_sc`, `pemazyre_oral`, `pyrukynd_oral`, `sirturo_oral`, `tabrecta_oral`, `talzenna_oral`, `vitrakvi_oral`, `vivjoa_oral`, `xadago_oral`, `zydelig_oral`

### Generic / biosimilar dispensed within 3 years of first Rx (0)
Out of scope (no generic entry in the first 3 years).

### No ATC class (narrow) (26)
RxClass has no ATC code yet (often recent approvals); fill by hand.
`aemcolo_oral`, `akynzeo_oral`, `avmapkifakzynjacopack_oral`, `brinsupri_oral`, `crenessity_oral`, `cresemba_oral`, `ensacove_oral`, `forzinity_sc`, `gattex_sc`, `ibtrozi_oral`, `inluriyo_oral`, `journavx_oral`, `komzifti_oral`, `modeyso_oral`, `myqorzo_oral`, `nereus_oral`, `nuzolvence_oral`, `paxlovid_oral`, `redemplo_sc`, `tavalisse_oral`, `tryngolza_sc`, `vanrafia_oral`, `veltassa_oral`, `wayrilz_oral`, `xermelo_oral`, `zegfrovy_oral`

### Several ATC classes (narrow) (9)
Still more than one class after dropping combination-product and topical / eye classes (pipeline/rxclass.py). Analyses that need one class should check these.
`duavee_oral`, `ella_oral`, `genvoya_oral`, `natazia_oral`, `nextstellis_oral`, `rystiggo_sc`, `stribild_oral`, `tabrecta_oral`, `tepmetko_oral`

### Brands with two route groups (4)
Each route group is its own analog; check which one launched first.
`ozempic_oral`, `ozempic_sc`, `sunlenca_oral`, `sunlenca_sc`

## NDC matching
- application_number: 1097
- application_number; route inferred: 321
- application_number; route from Drugs@FDA: 93
- sdud labeler + name: 2

## Label-read values (data/reference/analog_evidence.csv)
31 values for 8 analogs; 27 approved, 4 waiting for review.

### Analogs with unapproved values (4)
`otezla_oral`, `skyrizi_sc`, `sotyktu_oral`, `tremfya_sc`

### Launch date vs first SDUD Rx quarter differ by > 1 quarter (1)
`ibrance_oral`
