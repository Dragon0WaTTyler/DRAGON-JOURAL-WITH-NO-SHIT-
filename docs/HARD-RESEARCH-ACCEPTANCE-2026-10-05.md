# Hard research allocation acceptance — 2026-10-05

Base: canonical main `393eee6dfaf69088409ff80bad2e47f9000db1f5`.
This focused follow-up does not reopen repository migration or activate production.

## Root cause and execution trace

The previous 18 ACCOUNTABILITY / 15 SERVICE counts are required **acquisitions**,
not search-engine calls. Each lane has three search requests and one configured
canonical-navigation fetch. Exact provider pages and discovered child requests
also enter the finality obligation ledger. The recorded run executed only three
searches in total, while consuming its full 16-action ceiling.

Unresolved hard targets originate in the readiness configuration. `provider_targeting`
projects them into the ordered, dated research request; `providers` renders the
semantics, exclusions, current-operation guidance and discovery-only warning into
the actual provider prompt. The provider supplies unverified candidate URLs and
reported attempts, not native scheduler authority. `research_planning` materializes
hard semantic breadth, `research_recovery` makes function-specific acquisition needs,
and `deep_research` creates bounded STANDARD jobs. `query_ladder` emits route-scoped,
primary-window, canonical-navigation and alternate-language strategies.

`schedule_research_actions` previously ranked PROVIDER_EXACT before native ladders,
reserved complementary role pages, then alternated hard lanes. In epoch 0 that
admitted four hard provider fetches, one general provider fetch and three searches.
Search results materialized required exact child inspections. Continuation preserved
IDs, counters and strategy indices; children inherited their parent index (zero or
one). Those children sorted ahead of pending core steps two/three in epoch 1,
consuming all eight slots. No new provider call, truncation, duplicate suppression,
early closure, or larger optional discovery wave caused those omissions.

The executor's shared RoundActionBudget protected selected requests from recursive
follow-ups. The initial and one delta/recovery epoch each remained capped at eight.
Per-job search/fetch/follow-up allowances and max rounds stayed finite. Changed or
renumbered recovery needs preserve separate lineage; unchanged needs carry exact
obligations without resetting counters. Deferred work remains visible to finality.
Every required unexecuted concrete follow-up prevents an absence closure.

Search discovery becomes a candidate lead only. A selected child passes ordinary
URL safety, extraction, source-role/origin, event matching, temporal/current-operation,
semantic and claim-evidence checks. `build_research_finality` consumes accepted
bundles and exact hash-bound observations; navigation, metadata and provider role
labels cannot close a lane.

## Allocation rule

Only an active mandatory protocol uses core-first admission. Native ordered ladder
steps precede provider candidate pages and inherited child requests; lanes alternate
within the core tier and within the follow-up tier. A lane with no remaining core
does not reserve a child slot ahead of the other lane's core. Complementary role
fetches remain in the follow-up pool instead of jumping the core reservation.
The existing edition-wide general-discovery opportunity is retained. Core IDs
selected/deferred are recorded explicitly. Without a mandatory protocol the existing
exact-provider preference is retained.

PR #5's review identified that the initial sort key activated core-first behavior
for both hard lanes whenever either lane was mandatory. The key now tests the lane
being sorted: `lane not in mandatory_lanes`. The four-case regression covers both
mandatory, only ACCOUNTABILITY, only SERVICE, and neither. Optional lanes retain
their provider PRIMARY page and complementary INDEPENDENT page preference. The
same regression checks all eight slots, complete selected/deferred accounting,
unchanged configuration and untouched job counters. The two single-lane cases
failed before the fix and all four pass after it.

Both initial and recovery execution dispatch selected jobs in their first scheduled
appearance order. Previously the executor grouped by job, then iterated original
materialization order, allowing a general job to run before hard jobs. Jobs remain
serial and retain their original IDs, counters and selected actions.

No ladder variant, obligation, evidence gate, deferred record or expectation was
removed. All budget files are unchanged: STANDARD job allowances remain four
searches, four fetches, four lead follow-ups and two rounds; each global epoch remains
eight actions, with at most two epochs (16 total). A discovered obligation universe
larger than available capacity can still block; it is never relabeled exhausted.

## Previous slot ledger

Execution order below follows the recorded executor report (jobs execute serially).

| Epoch | Slot | Lane | Type | Action ID | Target |
|---|---:|---|---|---|---|
| 0 | 1 | GENERAL | FETCH_URL | `ACT-75B045B99ED4` | https://www.maroc.ma/fr/actualites/le-conseil-national-du-pam-mandate-sa-commission-chargee-des-consultations-pour-poursuivre-les |
| 0 | 2 | ACCOUNTABILITY | FETCH_URL | `ACT-0D26A8B1246E` | https://conseil-concurrence.ma/communique-du-conseil-de-la-concurrence-relatif-au-projet-de-concentration-economique-concernant-lacquisition-par-la-societe-societe-nouvelle-des-minoteries-itrane-sndmi-du-fo/ |
| 0 | 3 | ACCOUNTABILITY | FETCH_URL | `ACT-ECBE75E0E7FF` | https://medias24.com/2026/10/02/minoterie-chakib-alj-veut-reprendre-lactivite-ditrane-a-inezgane-1770285/ |
| 0 | 4 | SERVICE | FETCH_URL | `ACT-D153598A8177` | https://www.men.gov.ma/fr/actualites/rappel-des-dates-de-la-rentr%C3%A9e-scolaire-2026/2027 |
| 0 | 5 | SERVICE | FETCH_URL | `ACT-8658346A92B5` | https://fr.belpresse.com/a-la-une/rentree-scolaire-2026-2027-le-ministere-confirme-le-calendrier-officiel/ |
| 0 | 6 | ACCOUNTABILITY | SEARCH_DISCOVERY | `ACT-A16394ED2F88` | site:courdescomptes.ma Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر هيئة تنظيمية قرار active 2026-10 |
| 0 | 7 | ACCOUNTABILITY | SEARCH_DISCOVERY | `ACT-9E2660B67AF7` | Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر مجلس حسابات تقرير active 2026-10 |
| 0 | 8 | SERVICE | SEARCH_DISCOVERY | `ACT-318ACC4BA760` | site:maroc.ma Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر وزارة بلاغ رسمي active deadline 2026-10 |
| 1 | 1 | ACCOUNTABILITY | FETCH_URL | `ACT-A3B975CADB7B` | https://www.courdescomptes.ma/en/notice/assessing-the-relevance-of-public-policies-and-programs-the-court-of-accounts-hosts-the-annual-meeting-of-the-intosai-working-group/ |
| 1 | 2 | ACCOUNTABILITY | FETCH_URL | `ACT-1C04E5CEFF40` | https://www.alalam.ma/%D8%A3%D9%83%D8%AA%D9%88%D8%A8%D8%B1-%D8%A7%D9%84%D9%88%D8%B1%D8%AF%D9%8A-%D9%88%D8%B2%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D8%B5%D8%AD%D8%A9-%D8%AA%D8%AF%D8%B9%D9%88-%D8%A5%D9%84%D9%89-%D8%A7%D9%84%D9%83%D8%B4%D9%81-%D8%A7%D9%84%D9%85%D8%A8%D9%83%D8%B1-%D8%B9%D9%86-%D8%B3%D8%B1%D8%B7%D8%A7%D9%86%D9%8A-%D8%A7%D9%84%D8%AB%D8%AF%D9%8A_a35187.html |
| 1 | 3 | ACCOUNTABILITY | FETCH_URL | `ACT-202E9B378D12` | https://canal212.ma/ar/octobre-rose-maroc-ministere-sante-depistage-precoce/ |
| 1 | 4 | ACCOUNTABILITY | FETCH_URL | `ACT-39DEE9125562` | https://ar.le360.ma/societe/6XOKLJJKMND5VFY6NJ4PGP3MGY/ |
| 1 | 5 | SERVICE | FETCH_URL | `ACT-1E5304B10F33` | https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A7%D8%B3%D8%AA%D8%B1%D8%A7%D8%AA%D9%8A%D8%AC%D9%8A%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9 |
| 1 | 6 | SERVICE | FETCH_URL | `ACT-3ADB0E72B48E` | https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A7%D8%B3%D8%AA%D8%B1%D8%A7%D8%AA%D9%8A%D8%AC%D9%8A%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9/%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9-%D9%81%D9%8A-%D9%85%D8%AC%D8%A7%D9%84-%D8%A7%D9%84%D8%B5%D8%AD%D8%A9-%D9%88%D8%A7%D9%84%D8%AD%D9%85%D8%A7%D9%8A%D8%A9-%D8%A7%D9%84%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%D9%8A%D8%A9 |
| 1 | 7 | SERVICE | FETCH_URL | `ACT-51ABA660848B` | https://niya.maroc.ma/%D8%A7%D9%84%D9%85%D9%86%D8%AA%D8%AE%D8%A8-%D8%A7%D9%84%D9%85%D8%BA%D8%B1%D8%A8%D9%8A-%D9%84%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D9%82%D8%AF%D9%85-%D9%84%D8%A3%D9%82%D9%84-%D9%85%D9%86-23-%D8%B3%D9%86/ |
| 1 | 8 | SERVICE | FETCH_URL | `ACT-5FC48B505F94` | https://www.maroc.ma/ar/%D8%A7%D9%84%D8%B3%D9%86%D8%A9-%D8%A7%D9%84%D8%AC%D8%AF%D9%8A%D8%AF%D8%A9 |

## Every previous required acquisition

Targets are untrusted recorded retrieval inputs, not verified reporting. Order is
the parent strategy index; child identity and URL distinguish inherited indices.
E0 omitted core work was displaced by five provider/general pages; E1 omitted core
work was displaced by eight child fetches. Other missing children could not fit
after those eight selected inspections. Core search/fetch allowances were not
exhausted; the four-child allowance in each hard job was spent in epoch 1.

| Lane | Order | Planned/discovered epoch | Admitted epoch | Executed epoch | Action ID | Type / target | Missing reason |
|---|---:|---|---|---|---|---|---|
| ACCOUNTABILITY | 0 | [0] | [0] | 0 | `ACT-0D26A8B1246E` | FETCH_URL: https://conseil-concurrence.ma/communique-du-conseil-de-la-concurrence-relatif-au-projet-de-concentration-economique-concernant-lacquisition-par-la-societe-societe-nouvelle-des-minoteries-itrane-sndmi-du-fo/ | — |
| ACCOUNTABILITY | 1 | [0] | [0] | 0 | `ACT-ECBE75E0E7FF` | FETCH_URL: https://medias24.com/2026/10/02/minoterie-chakib-alj-veut-reprendre-lactivite-ditrane-a-inezgane-1770285/ | — |
| ACCOUNTABILITY | 0 | [0] | [0] | 0 | `ACT-A16394ED2F88` | SEARCH_DISCOVERY: site:courdescomptes.ma Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر هيئة تنظيمية قرار active 2026-10 | — |
| ACCOUNTABILITY | 1 | [0] | [0] | 0 | `ACT-9E2660B67AF7` | SEARCH_DISCOVERY: Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر مجلس حسابات تقرير active 2026-10 | — |
| ACCOUNTABILITY | 2 | [0, 1] | [] | DEFERRED | `ACT-AD9307C18DBD` | FETCH_CONFIGURED_SOURCE: https://www.courdescomptes.ma/publications/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 3 | [0, 1] | [] | DEFERRED | `ACT-1CAFE050C849` | SEARCH_DISCOVERY: Morocco أكتوبر election integrity September 2026 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 0 | [1] | [1] | 1 | `ACT-A3B975CADB7B` | FETCH_URL: https://www.courdescomptes.ma/en/notice/assessing-the-relevance-of-public-policies-and-programs-the-court-of-accounts-hosts-the-annual-meeting-of-the-intosai-working-group/ | — |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-B86C4027B2EF` | FETCH_URL: https://maacom.ma/2026/10/01/%D8%A3%D9%83%D8%AA%D9%88%D8%A8%D8%B1-%D8%A7%D9%84%D9%88%D8%B1%D8%AF%D9%8A-%D9%88%D8%B2%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D8%B5%D8%AD%D8%A9-%D8%AA%D8%AC%D8%AF%D8%AF-%D8%A7%D9%84%D8%AF%D8%B9%D9%88%D8%A9/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-B16268A1827D` | FETCH_URL: https://journalinfo.ma/159791 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [1] | 1 | `ACT-39DEE9125562` | FETCH_URL: https://ar.le360.ma/societe/6XOKLJJKMND5VFY6NJ4PGP3MGY/ | — |
| ACCOUNTABILITY | 1 | [1] | [1] | 1 | `ACT-1C04E5CEFF40` | FETCH_URL: https://www.alalam.ma/%D8%A3%D9%83%D8%AA%D9%88%D8%A8%D8%B1-%D8%A7%D9%84%D9%88%D8%B1%D8%AF%D9%8A-%D9%88%D8%B2%D8%A7%D8%B1%D8%A9-%D8%A7%D9%84%D8%B5%D8%AD%D8%A9-%D8%AA%D8%AF%D8%B9%D9%88-%D8%A5%D9%84%D9%89-%D8%A7%D9%84%D9%83%D8%B4%D9%81-%D8%A7%D9%84%D9%85%D8%A8%D9%83%D8%B1-%D8%B9%D9%86-%D8%B3%D8%B1%D8%B7%D8%A7%D9%86%D9%8A-%D8%A7%D9%84%D8%AB%D8%AF%D9%8A_a35187.html | — |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-B4667E62F57C` | FETCH_URL: https://www.dakhlatv.com/news-56169 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-53BB8B5F6C19` | FETCH_URL: https://www.20minutes.ma/society/172199.html | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [1] | 1 | `ACT-202E9B378D12` | FETCH_URL: https://canal212.ma/ar/octobre-rose-maroc-ministere-sante-depistage-precoce/ | — |
| ACCOUNTABILITY | 0 | [1] | [] | DEFERRED | `ACT-F35990383CC5` | FETCH_URL: https://www.courdescomptes.ma/en/presentation-2/reports-of-the-court/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-43E6065E8642` | FETCH_URL: https://www.alalam.ma/تكنولوجيا-وعلوم_r20.html | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-3C7E24B4494C` | FETCH_URL: https://www.alalam.ma/feeds/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| ACCOUNTABILITY | 1 | [1] | [] | DEFERRED | `ACT-8ED0CF141E78` | FETCH_URL: https://canal212.ma/ar/category/sinstaller-au-maroc/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [0] | [0] | 0 | `ACT-D153598A8177` | FETCH_URL: https://www.men.gov.ma/fr/actualites/rappel-des-dates-de-la-rentr%C3%A9e-scolaire-2026/2027 | — |
| SERVICE | 1 | [0] | [0] | 0 | `ACT-8658346A92B5` | FETCH_URL: https://fr.belpresse.com/a-la-une/rentree-scolaire-2026-2027-le-ministere-confirme-le-calendrier-officiel/ | — |
| SERVICE | 0 | [0] | [0] | 0 | `ACT-318ACC4BA760` | SEARCH_DISCOVERY: site:maroc.ma Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر وزارة بلاغ رسمي active deadline 2026-10 | — |
| SERVICE | 1 | [0, 1] | [] | DEFERRED | `ACT-836E037E9070` | SEARCH_DISCOVERY: Morocco أكتوبر الوردي: حملة للتعريف بالوقاية والكشف المبكر إدارة الانتخابات مكتب active deadline 2026-10 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 2 | [0, 1] | [] | DEFERRED | `ACT-E7A52108BF60` | FETCH_CONFIGURED_SOURCE: https://maroc.ma/en/news | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 3 | [0, 1] | [] | DEFERRED | `ACT-EB0CC1603B90` | SEARCH_DISCOVERY: Morocco أكتوبر administrative portal deadline September 2026 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [1] | [] | DEFERRED | `ACT-9BC6808735E4` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1/%D8%A7%D9%84%D8%AD%D9%85%D9%84%D8%A9-%D8%A7%D9%84%D8%A7%D9%86%D8%AA%D8%AE%D8%A7%D8%A8%D9%8A%D8%A9-%D8%B6%D9%88%D8%A7%D8%A8%D8%B7-%D9%82%D8%A7%D9%86%D9%88%D9%86%D9%8A%D8%A9-%D9%88%D8%A5%D8%AC%D8%B1%D8%A7%D8%A1%D8%A7%D8%AA-%D8%B2%D8%AC%D8%B1%D9%8A%D8%A9-%D9%85%D9%86-%D8%A3%D8%AC%D9%84-%D8%A7%D9%82%D8%AA%D8%B1%D8%A7%D8%B9-%D9%86%D8%B2%D9%8A%D9%87-%D9%88%D8%B4%D9%81%D8%A7%D9%81 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [1] | [1] | 1 | `ACT-5FC48B505F94` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%B3%D9%86%D8%A9-%D8%A7%D9%84%D8%AC%D8%AF%D9%8A%D8%AF%D8%A9 | — |
| SERVICE | 0 | [1] | [] | DEFERRED | `ACT-EA77B918162C` | FETCH_URL: https://niya.maroc.ma/%D8%A7%D9%84%D8%AE%D8%B7%D8%A8-%D9%88%D8%A7%D9%84%D8%B1%D8%B3%D8%A7%D8%A6%D9%84-%D8%A7%D9%84%D9%85%D9%84%D9%83%D9%8A%D8%A9/%D8%B1%D8%B3%D8%A7%D9%84%D8%A9-%D9%85%D9%84%D9%83%D9%8A%D8%A9-%D8%A5%D9%84%D9%89-%D8%A7%D9%84%D9%85%D9%86%D8%A7%D8%B8%D8%B1%D8%A9/ | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [1] | [1] | 1 | `ACT-51ABA660848B` | FETCH_URL: https://niya.maroc.ma/%D8%A7%D9%84%D9%85%D9%86%D8%AA%D8%AE%D8%A8-%D8%A7%D9%84%D9%85%D8%BA%D8%B1%D8%A8%D9%8A-%D9%84%D9%83%D8%B1%D8%A9-%D8%A7%D9%84%D9%82%D8%AF%D9%85-%D9%84%D8%A3%D9%82%D9%84-%D9%85%D9%86-23-%D8%B3%D9%86/ | — |
| SERVICE | 0 | [1] | [1] | 1 | `ACT-3ADB0E72B48E` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A7%D8%B3%D8%AA%D8%B1%D8%A7%D8%AA%D9%8A%D8%AC%D9%8A%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9/%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9-%D9%81%D9%8A-%D9%85%D8%AC%D8%A7%D9%84-%D8%A7%D9%84%D8%B5%D8%AD%D8%A9-%D9%88%D8%A7%D9%84%D8%AD%D9%85%D8%A7%D9%8A%D8%A9-%D8%A7%D9%84%D8%A7%D8%AC%D8%AA%D9%85%D8%A7%D8%B9%D9%8A%D8%A9 | — |
| SERVICE | 0 | [1] | [1] | 1 | `ACT-1E5304B10F33` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A7%D8%B3%D8%AA%D8%B1%D8%A7%D8%AA%D9%8A%D8%AC%D9%8A%D8%A7%D8%AA-%D9%88%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D8%A7%D8%AA-%D8%A7%D9%84%D8%B9%D9%85%D9%88%D9%85%D9%8A%D8%A9 | — |
| SERVICE | 0 | [1] | [] | DEFERRED | `ACT-9F1EBC3B8F8E` | FETCH_URL: https://www.maroc.ma/en/strategies-and-public-policies/public-policies-health-and-social-protection | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [1] | [] | DEFERRED | `ACT-D273F71279BE` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1/%D8%A7%D9%84%D9%85%D8%AC%D9%84%D8%B3-%D8%A7%D9%84%D9%88%D8%B7%D9%86%D9%8A-%D9%84%D8%AD%D8%B2%D8%A8-%D8%A7%D9%84%D8%AD%D8%B1%D9%83%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%8A%D9%81%D9%88%D8%B6-%D8%A7%D9%84%D8%A3%D9%85%D9%8A%D9%86-%D8%A7%D9%84%D8%B9%D8%A7%D9%85-%D9%85%D9%88%D8%A7%D8%B5%D9%84%D8%A9-%D8%A7%D9%84%D9%85%D8%B4%D8%A7%D9%88%D8%B1%D8%A7%D8%AA-%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D9%8A%D8%A9-%D9%88%D8%A7%D8%AA%D8%AE%D8%A7%D8%B0-%D8%A7%D9%84%D9%82%D8%B1%D8%A7%D8%B1-%D8%A7%D9%84%D9%85%D9%84%D8%A7%D8%A6%D9%85 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |
| SERVICE | 0 | [1] | [] | DEFERRED | `ACT-AC8C34B337F0` | FETCH_URL: https://www.maroc.ma/ar/%D8%A7%D9%84%D8%A3%D8%AE%D8%A8%D8%A7%D8%B1/%D8%A7%D9%84%D9%85%D8%AC%D9%84%D8%B3-%D8%A7%D9%84%D9%88%D8%B7%D9%86%D9%8A-%D9%84%D8%AD%D8%B2%D8%A8-%D8%A7%D9%84%D8%AD%D8%B1%D9%83%D8%A9-%D8%A7%D9%84%D8%B4%D8%B9%D8%A8%D9%8A%D8%A9-%D9%8A%D9%81%D9%88%D8%B6-%D8%A7%D9%84%D8%A3%D9%85%D9%8A%D9%86-%D8%A7%D9%84%D8%B9%D8%A7%D9%85-%D9%85%D9%88%D8%A7%D8%B5%D9%84%D8%A9-%D8%A7%D9%84%D9%85%D8%B4%D8%A7%D9%88%D8%B1%D8%A7%D8%AA-%D8%A7%D9%84%D8%B3%D9%8A%D8%A7%D8%B3%D9%8A%D8%A9-%D9%88%D8%A7%D8%AA%D8%AE%D8%A7%D8%B0-%D8%A7%D9%84%D9%82%D8%B1%D8%A7%D8%B1-%D8%A7%D9%84%D9%85%D9%84%D8%A7%D8%A6%D9%85 | ROUND_CAP_PRESERVES_SELECTED_ACTIONS / ROUND_BUDGET_PRIORITY_AND_FAIRNESS |

## Offline regression and feasibility

The scheduling-only fixture preserves public request identities from the previous
run, without provider responses or evidence assertions. It records the original
admissions and tests new exact admission/order semantics against those inputs.
The epoch-0 regression admits seven core steps plus the retained general opportunity;
the regression from the actual old epoch-1 checkpoint admits all five pending core
steps before three children. These are prospective offline allocations, not a new
research result. A separate two-epoch fixture executes ordered ladders with unchanged
job counters and verifies carry-forward and deterministic scheduling.

The previous obligation universe was 33 hard acquisitions plus one general action.
Completing all 34 is mathematically impossible under a 16-action ceiling unless
valid evidence closes a lane or an exact same-artifact reuse is genuinely proved.
The change fixes core starvation; it cannot promise complete inspection of arbitrary
numbers of discovered leads. Genuine residual scarcity remains a truthful blocker.

Browser requalification retained its previous receipt and performed fresh operational
HTTPS and fixed offline JS probes plus 68 containment/control tests. It used zero
provider calls and zero research actions. The hash-bound guard was not bypassed.

## Validation and one fresh live result

Targeted offline research checks: 167 passed in 24.13 seconds. Provider acceptance:
9 passed in 13.06 seconds. Browser controls: 68 passed in 3.75 seconds.
Full suite: 1,000 passed, zero failed, two existing Windows native-rendering skips
in 306.46 seconds, Windows 11 / CPython 3.14.5. Existing test assertions and skip
conditions remain intact.

### Sole new live trial: execution not accepted

Run: `provider-research-acceptance-4dda6883-7f84-4c3c-be34-2c9e0ff419e0`.
Edition/as-of date: `2026-10-05`; technical validation after the production deadline.
Source revision: `9fbff2efa15a45162821c9309b877172ccbdd521`.
Provider invocation: one call, zero retries, normalized. Request began at
22:21:32 UTC; response returned at 22:29:50 UTC. The actual saved request/prompt
contains the ordered ACCOUNTABILITY then SERVICE targets, `as_of_date`, both HARD
IDs, semantics, exclusions, current-operation guidance and discovery-only warnings.
Provider-reported searches (four ACCOUNTABILITY, five SERVICE) are not independently
observed native searches and do not satisfy native required acquisition obligations.

Initial admission: eight actions (five searches, three fetches, zero children).
Thirty-seven planned actions were deferred: one ACCOUNTABILITY provider page,
one SERVICE alternate-language core search, and 35 general actions. The shared
round cap remained eight. Epoch 1 was never reached.

| Scheduled position | Lane | Order | Type | Action ID |
|---:|---|---:|---|---|
| 1 | ACCOUNTABILITY | 0 | SEARCH_DISCOVERY | `ACT-820A7CD499C9` |
| 2 | SERVICE | 0 | SEARCH_DISCOVERY | `ACT-9D97188D8BF5` |
| 3 | GENERAL | 0 | FETCH_URL | `ACT-6A7B22B3497B` |
| 4 | ACCOUNTABILITY | 1 | SEARCH_DISCOVERY | `ACT-64CB89EA296E` |
| 5 | SERVICE | 1 | SEARCH_DISCOVERY | `ACT-A5F5A5F9BEE4` |
| 6 | ACCOUNTABILITY | 2 | FETCH_CONFIGURED_SOURCE | `ACT-661026B8E4FD` |
| 7 | SERVICE | 2 | FETCH_CONFIGURED_SOURCE | `ACT-67CBE052C75E` |
| 8 | ACCOUNTABILITY | 3 | SEARCH_DISCOVERY | `ACT-C44887CCD647` |

SERVICE order 3 (`ACT-97B3168947F2`) remained explicitly deferred for continuation.
Each lane's core ladder requires three searches and one canonical-navigation fetch.
No hard search actually ran in this attempt.

The stage failed with `UNHANDLED_STAGE_EXCEPTION` at the unknown-role event feedback
query: `skeleton.get("published_at", "")[:7]` attempted to slice an explicit null.
A current event can legitimately have an effective/event date and no publication
date. The failure occurred while processing the general Rotork competition notice
fetch, before either hard job. The old dispatch loop ran materialized GENERAL first,
even though ACCOUNTABILITY was first in the scheduler. The selected-action budget
protected the seven remaining requests from recursive follow-ups. Thus **one native
fetch, zero searches and zero child fetches** can be derived from the traceback,
job queue and admission guard. These are derived counts, not a persisted execution
ledger: the exception prevented `execution-report.json` and finality from being
written. Full execution replay is unavailable for that reason.

The offline reproducer establishes the same null-date exception. The one-line fix
uses `(skeleton.get("published_at") or "")[:7]`; it neither invents a date nor
promotes unknown source roles. A regression proves the event stays unqualified,
feedback stays bounded, and no publication date is fabricated. A pipeline integration
regression proves scheduler job order survives execution despite GENERAL appearing
first in materialization. Both execution epochs use the same dispatch rule.

ACCOUNTABILITY normalization retained two unverified candidates:
`investigations-01` (UK statement on the Sudan resolution,
https://www.gov.uk/government/speeches/un-human-rights-council-63-introductory-statement-on-the-draft-resolution-on-sudan,
with Sudan Tribune candidate independent source https://sudantribune.com/article/319647)
and `investigations-02` (Moroccan Competition Council Rotork/ABB notice,
https://conseil-concurrence.ma/communique-du-conseil-de-la-concurrence-relatif-au-projet-de-concentration-economique-concernant-la-prise-de-controle-exclusif-de-la-societe-rotork-plc-par-la-societe-abb-ltd/).
These are provider claims, not accepted artifact evidence. SERVICE proposed that
second candidate, which normalization rejected as `HARD_TARGET_CANDIDATE_MISMATCH`:
it is not an auditable SERVICE candidate. Its effective disposition remains
`CONTRACT_VIOLATION_NO_VALID_CANDIDATES`. No SERVICE exact candidate survived.

Neither lane reached hard artifact inspection, child verification, source-origin
qualification, evidence gate or closure. No artifact was selected as accepted;
no role label became validated PRIMARY/INDEPENDENT evidence. The execution stage
is FAILED, recovery is PENDING, final research finality was not produced, and article
or publication stages did not execute.

The sealed failed-run archive verifies PASS for all 79 preserved artifacts.
Manifest SHA-256: `ddd480afda6ad10da4e7b3f46b99c6793860aab8aa688e9ba871b2f7697761ba`.
Raw response SHA-256: `469c89632ca3ee66899405a42d9d1d1bdfef8ecae9558dbd6e37a27e1d798b38`.
Archive completeness does not mean research acceptance. Raw evidence and browser
proofs remain host-local and uncommitted; the failed record is immutable.

### Post-failure offline validation

The follow-up changes receive offline verification only; no second provider or live
research attempt is authorized by this task. Targeted research/targeting/acceptance
tests after the mandatory-lane review fix: 181 passed in 40.19 seconds, including
ten capacity/dispatch/null-date cases. Browser containment/control tests: 68 passed
in 3.59 seconds. Final full suite: 1,005 passed, zero failed, two existing Windows
native-rendering skips in 288.53 seconds (1,007 collected), Windows 11
`10.0.26300-SP0`, CPython 3.14.5. The earlier follow-up suite before the review fix
also passed (1,002 passed, two skipped, 300.72 seconds). No original assertion or
skip condition was changed. Final operational browser requalification used no
provider calls or research actions and retained its prior receipt.

Final task verdict: `HARD_SEARCH_EXECUTION_NOT_ACCEPTED`.
Overall production verdict remains `CUTOVER_COMPLETE_PRODUCTION_NOT_YET_ACCEPTED`.
Production automation remains paused. A later explicitly authorized bounded live
run must establish execution and evidence outcomes for the final implementation.
