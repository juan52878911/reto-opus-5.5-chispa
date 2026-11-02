# W4 (a) orientación de score (max_tok 256)

## Veredicto: el modelo ordena bien en el meta y no generaliza a JevBench

ρ meta = 0.12 frente a ρ JevBench = -0.52, con la conversión de JevBench correcta

Conversión de JevBench: correcta en los 18 casos score

## jevbench (n = 18, 7 esquemas)

| torre | ρ medio por esquema | exactitud CORAL |
|---|---|---|
| nivel máximo (actual) | -0.524 | 0.333 |
| nivel mínimo | -0.655 | 0.278 |
| s invertida (−s) | 0.524 | 0.278 |
| clase mayoritaria | | 0.556 |

| esquema | K | n | w | ρ máx | ρ mín | ρ −s | ex. máx | ex. mín | ex. −s |
|---|---|---|---|---|---|---|---|---|---|
| jev:4511e47344 | 5 | 1 | 3.95 | — | — | — | 1.000 | 0.000 | 0.000 |
| jev:4bfd05e7fa | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 0.000 |
| jev:63d23e6a93 | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 0.000 |
| jev:88c2b9c394 | 4 | 1 | 3.94 | — | — | — | 1.000 | 1.000 | 0.000 |
| jev:8fb226adc2 | 4 | 12 | 3.94 | -0.524 | -0.655 | 0.524 | 0.333 | 0.333 | 0.333 |
| jev:c015c7d85b | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 0.000 |
| jev:cdbcfe3d27 | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 1.000 |

## meta (n = 699, 91 esquemas)

| torre | ρ medio por esquema | exactitud CORAL |
|---|---|---|
| nivel máximo (actual) | 0.123 | 0.215 |
| nivel mínimo | 0.146 | 0.225 |
| s invertida (−s) | -0.123 | 0.246 |
| clase mayoritaria | | 0.488 |

| esquema | K | n | w | ρ máx | ρ mín | ρ −s | ex. máx | ex. mín | ex. −s |
|---|---|---|---|---|---|---|---|---|---|
| FOL-nli | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| HelpSteer/coherence | 5 | 2 | 3.95 | — | — | — | 1.000 | 0.500 | 0.000 |
| HelpSteer/correctness | 5 | 1 | 3.95 | — | — | — | 0.000 | 0.000 | 0.000 |
| HelpSteer/helpfulness | 5 | 1 | 3.95 | — | — | — | 1.000 | 1.000 | 0.000 |
| HelpSteer/verbosity | 5 | 1 | 3.95 | — | — | — | 1.000 | 1.000 | 0.000 |
| HelpSteer2/coherence | 5 | 3 | 3.95 | — | — | — | 0.000 | 0.000 | 0.000 |
| HelpSteer2/complexity | 3 | 3 | 3.86 | 0.866 | 0.866 | -0.866 | 0.333 | 0.333 | 0.000 |
| HelpSteer2/correctness | 4 | 3 | 3.94 | 1.000 | 0.500 | -1.000 | 0.000 | 0.000 | 0.333 |
| HelpSteer2/helpfulness | 5 | 1 | 3.95 | — | — | — | 0.000 | 0.000 | 0.000 |
| HelpSteer2/verbosity | 5 | 2 | 3.95 | — | — | — | 0.000 | 0.000 | 0.000 |
| HelpSteer3/feedback | 5 | 3 | 3.95 | -0.500 | -1.000 | 0.500 | 0.000 | 0.000 | 0.000 |
| HelpSteer3/preference_strength | 7 | 2 | 4.01 | — | — | — | 0.000 | 0.000 | 0.000 |
| MSciNLI | 5 | 1 | 3.95 | — | — | — | 0.000 | 0.000 | 0.000 |
| SpaceNLI | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 0.000 |
| TuringBench | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 1.000 |
| WANLI | 3 | 2 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| acceptability-prediction/rating_votes | 4 | 45 | 3.94 | 0.288 | 0.261 | -0.288 | 0.267 | 0.222 | 0.311 |
| acord | 5 | 24 | 3.95 | -0.316 | -0.286 | 0.316 | 0.000 | 0.000 | 0.958 |
| autotnli | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| blog_authorship_corpus/gender | 3 | 2 | 3.86 | — | — | — | 0.000 | 0.000 | 1.000 |
| cebab/rating | 5 | 4 | 3.95 | -0.211 | -0.211 | 0.211 | 0.000 | 0.000 | 0.000 |
| commonsense_qa_2.0 | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 1.000 |
| conceptrules_v2 | 4 | 1 | 3.94 | — | — | — | 1.000 | 1.000 | 0.000 |
| corr2cause | 3 | 3 | 3.86 | -0.866 | -0.866 | 0.866 | 0.333 | 0.333 | 0.667 |
| dnd_style_intents | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 1.000 |
| doc-nli | 3 | 6 | 3.86 | 0.414 | 0.414 | -0.414 | 0.000 | 0.000 | 0.333 |
| emo/emo2019 | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| github-issue-similarity | 4 | 1 | 3.94 | — | — | — | 1.000 | 1.000 | 0.000 |
| go_emotions/simplified | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 1.000 |
| hallmarks-of-cancer/yesno | 3 | 2 | 3.86 | — | — | — | 0.500 | 0.500 | 0.000 |
| hope_edi/english | 4 | 1 | 3.94 | — | — | — | 0.000 | 0.000 | 0.000 |
| hyperpartisan_news | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| lex_glue/unfair_tos | 3 | 2 | 3.86 | — | — | — | 0.000 | 0.000 | 1.000 |
| magpie/idiomatic | 3 | 1 | 3.86 | — | — | — | 1.000 | 1.000 | 0.000 |
| mams/atsa | 3 | 10 | 3.86 | -0.161 | -0.289 | 0.161 | 0.300 | 0.300 | 0.400 |
| maud/specific-performance | 3 | 1 | 3.86 | — | — | — | 0.000 | 0.000 | 0.000 |
| multilingual/AfriSenti-twitter-sentiment/amh | 3 | 1 | 3.86 | — | — | — | 1.000 | 1.000 | 0.000 |
| multilingual/AfriSenti-twitter-sentiment/ary | 3 | 1 | 3.86 | — | — | — | 1.000 | 1.000 | 0.000 |
| multilingual/AfriSenti-twitter-sentiment/hau | 3 | 1 | 3.86 | — | — | — | 1.000 | 1.000 | 0.000 |
| multilingual/AfriSenti-twitter-sentiment/kin | 3 | 1 | 3.86 | — | — | — | 1.000 | 1.000 | 0.000 |

