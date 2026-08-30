# Generalized location scraping and processing rework plan

**Status:** final implementation plan. This document describes the work to be done; it
does not itself implement the runner, migrate state, or delete production data.

**Repository snapshot reviewed:** branch `next-gen`, commit `8d61808`. The current
checkout was clean when this plan was updated. Counts and remote-table assertions must
be rechecked immediately before the migration because the repository and the remote
DynamoDB table can change independently.

## 1. Decisions that are already settled

The following decisions are part of the target and must not be reopened by an
implementation agent:

1. **Supported locations are exactly seven:** Augustiner, Emil und Moritz, Galeria, Le
   Casino, Leo's, Moritzbastei, and Ratskeller. The stale orphan location represented by
   `data/milchbarpinguin/` is removed from the repository. It receives no configuration,
   migration entry, workflow, or website entry. Its old historical files are not
   preserved as an active location.
2. **The existing menu JSON contract remains the contract.** Do not introduce a new
   menu JSON schema, wrapper object, version field, or new meal fields. Existing prompts,
   day/week semantics, and historical JSON files remain usable. The new code may parse
   and validate the existing shape more safely, but it must not redesign it.
3. **DynamoDB remains deliberately small.** Continue using the existing `lunchdeal`
   table and its current key shape: the URL/tracking value in the `link` key and the
   Unix expiry value in the `timestamp` TTL field. New writes use only those two table
   fields. Do not add audit attributes, source-version attributes, status fields, or a
   second state table. Run metadata and lineage belong in temporary manifests and CI
   artifacts, not in DynamoDB.
4. **The default TTL is eight weeks.** A location configuration or an explicit CLI
   argument may override it with a positive number of weeks when there is a documented
   reason. An omitted override always means eight weeks. Migration uses eight weeks
   unless an operator records a deliberate override.
5. **Existing workflow container image references stay unchanged by default.** Do not
   replace, retag, or unify the images as part of the rework. If the new runner cannot
   execute in the current image because a genuinely required dependency or runtime
   change is missing, make the smallest necessary image change, publish a pinned image,
   update only the affected references, and record the reason and verification. An
   image update is an enabling change, not an independent cleanup task.
6. **The obsolete OCR-specific integration is not part of the target.** Remove its
   unused location helpers, package dependency, and stale documentation after a
   reference check confirms that no production path needs them. Do not replace it with
   another OCR subsystem as part of this rework; the current text and vision processing
   paths remain the source-specific implementations.
7. **Format drift is handled by ordered format variants, not by auto-detection
   magic.** Locations whose website switches menu formats over time (the known case is
   Le Casino: PDF → HTML → PDF) declare all known variants in their `location.yaml` as
   an ordered `formats:` list. The runner tries variants in order and uses the first
   one whose discovery succeeds. There is no content sniffing, no ML detection, and no
   parallel trying of variants. See section 3.5 for the full design and its complexity
   budget.

These decisions resolve the two intentionally simple interfaces: the menu result stays
as it is, and the state table stays a URL plus TTL. Additional information needed while
a run is in progress is carried by a manifest file and artifacts, not by expanding
those interfaces.

## 2. Objective, scope, and non-goals

The rework has one operational objective: replace duplicated shell/workflow state
handling with a small, testable pipeline that can run all seven supported locations and
use DynamoDB as the processed-content check without changing what the website consumes.

### 2.1 Current pain points (what the rework must fix)

- **Per-location workflow duplication.** Each of the seven location workflows
  (`.github/workflows/<location>.yaml`) re-implements the same download → process →
  publish stages with inline bash: `comm` against `data/<location>/scraped_done.txt`,
  `pdfseparate`/`pdftoppm` calls, jq matrix building, artifact juggling, and PR
  creation. A fix to shared logic (e.g. the state check) must be applied seven times.
- **Two parallel state mechanisms.** Some locations track processed links in
  `data/<location>/scraped_done.txt` (committed back via PR), others already use the
  DynamoDB `lunchdeal` table via `locations/.shared/dynamodb_link_validator.py`. The
  file-based mechanism is the duplication target; DynamoDB is the single mechanism
  going forward.
- **Configuration split across code.** A location's behavior is currently spread over
  `locations/<name>/config.py` (prompt kwargs), `prompt_overrides` (model
  provider/model), `prompt.txt`, `scra.py` (Scrapy spider with hardcoded URL and
  XPath), hardcoded shell in the workflow (PDF splitting, image conversion, output
  naming), and `data/<name>/details.json` (website display data). Nothing describes a
  location in one place.
- **Per-location `process_chatgpt.py` shims.** Each location has a near-identical
  script whose only real content is "load config, instantiate `DefaultMealChat`, call
  one method". Three locations additionally carry `process_textractor_result.py`
  helpers for the obsolete Textract path (decision 6).
- **Dead weight.** `data/milchbarpinguin/` (decision 1), the Textract helpers and
  their dependency, and stale docs.

### 2.2 In scope

1. A single YAML configuration per supported location under
   `locations/<name>/location.yaml`, covering: website target, scrape job, extraction
   pipeline, prompt, model, output naming, and TTL override.
2. A small Python runner package (working name `pipeline/`) with one CLI entry point
   (`python -m pipeline <location> <stage>` or an `all` mode) that executes the stages
   scrape → download → prepare → extract → publish, driven entirely by the location
   YAML plus shared defaults.
3. A shared location-config loader with schema validation and clear errors.
4. Consolidation of all processed-content state on the DynamoDB `lunchdeal` table,
   including a one-time migration of the `scraped_done.txt` entries.
5. One parameterized GitHub Actions workflow (reusable workflow or matrix workflow)
   replacing the seven per-location workflows.
6. Removal of `data/milchbarpinguin/`, the Textract helpers/dependency, and stale
   documentation, after reference checks.
7. Unit tests for the runner and config loader; the existing per-location prompt
   regression tests under `tests/<location>/` keep working against the new config.

### 2.3 Non-goals

- Changing the menu JSON schema or the website's consumption of `data/` (decision 2).
- Changing the DynamoDB table shape or adding attributes (decision 3).
- Retagging or unifying container images (decision 5).
- Introducing a new OCR subsystem (decision 6).
- Redesigning the website (`site/`) beyond what is needed to drop the Milchbar Pinguin
  entry.
- Adding new locations, new model providers, or prompt re-engineering. The prompts are
  moved, not rewritten, except where mechanical templating requires it.

## 3. Target architecture

### 3.1 Repository layout after the rework

```
locations/
  .shared/                     # unchanged shared helpers that are still needed
    DefaultMealChat.py         # (absorbed into pipeline/, see 3.4)
    prompt_config.py           # becomes shared defaults in YAML/py
  augustiner/
    location.yaml              # NEW: single source of truth for the location
    prompt.txt                 # kept when referenced by location.yaml
  emilundmoritz/
    location.yaml
    prompt.txt
  galeria/
    location.yaml
  lecasino/
    location.yaml
    prompt.txt
  leos/
    location.yaml
    prompt.txt
  moritzbastei/
    location.yaml
    prompt.txt
  ratskeller/
    location.yaml
    prompt.txt
pipeline/                      # NEW: the runner package
  __main__.py                  # CLI entry point
  config.py                    # YAML loading + validation + defaults
  stages/
    scrape.py                  # run spider / fetch links
    download.py                # download new content, record manifest
    prepare.py                 # pdfseparate / pdftoppm / text normalization
    extract.py                 # model call (text or vision) -> menu JSON
    publish.py                 # write data/<loc>/ JSONs, mark links processed
  state/
    dynamodb.py                # the only state backend (from .shared/dynamodb_link_validator.py)
  manifest.py                  # run manifest read/write
data/
  <location>/                  # unchanged contract: YYYY-WW.json + details.json
  # scraped_done.txt files are removed after migration
concepts/
  generalized-location-pipeline-plan.md   # this document
tests/
  <location>/                  # existing prompt regression tests, repointed at YAML
  pipeline/                    # NEW: unit tests for loader, stages, state
.github/workflows/
  location.yaml                # NEW: single parameterized workflow
  # the seven per-location workflows are deleted after cutover
```

### 3.2 The location YAML

Every configurable aspect of a location lives in `locations/<name>/location.yaml`.
The schema (all keys optional unless marked required; defaults shown):

```yaml
# locations/ratskeller/location.yaml (illustrative, matches current behavior)
name: Ratskeller Kantine            # required; display name, mirrors details.json
enabled: true                       # default true; false disables scheduling
website:
  url: https://ratskeller.restaurant/kantine-leipzig/speiseplan/   # required
  details:                          # optional; merged into details.json on publish
    - Kartenzahlung ja
scrape:
  type: scrapy                      # required; one of: scrapy | static | meta_refresh
  spider:                           # scrapy only: spider definition moved out of scra.py
    allowed_domains: [ratskeller.restaurant]
    link_xpath: '//section[.//a[contains(@href,"pdf")]][1]//a[contains(@href,"pdf")]/@href'
  # type: static would just fetch website.url; type: meta_refresh covers the
  # moritzbastei check_site_update.py mechanism
download:
  formats: [pdf]                    # which scraped links to download
prepare:                            # optional ordered pipeline of preparers
  - pdfseparate: {}                 # split multi-page PDFs into pages
  - pdftoppm: { resolution: 150, format: png, singlefile: true }
extract:
  type: vision                      # required; one of: vision | text
  input_file: image.png             # produced by prepare; or the text file for type: text
  prompt_file: prompt.txt           # optional; inline `prompt:` is the alternative
  prompt: |                         # optional; location-specific user message
    ...
  prompt_prefix: ""                 # optional; replaces userMessagePrefix
  add_current_date: false           # defaults from shared prompt config
  add_current_weekdays: true
  max_tokens: 5000
  model:
    provider: google                # model namespace: openai | google
    vision_model: vertex/gemini-2.5-flash-lite@europe-central2
    text_model: azure/gpt-5-mini@francecentral
publish:
  week_key_from: first_date         # how the output YYYY-WW.json name is derived
  ttl_weeks: 8                      # optional; omit = 8 (decision 4)
schedule:
  cron: '0 14 * * 0'                # consumed by the workflow generator/matrix
formats: []                         # optional ordered fallback variants (section 3.5)
```

Rules:

- The loader validates against a versioned schema (`schema_version: 1`) and fails the
  run with a precise error on unknown keys, wrong types, or missing required keys.
- Shared defaults (system prompt, JSON schema example, model defaults) live in exactly
  one place: `pipeline/defaults.yaml` (rendered from today's
  `locations/.shared/prompt_config.py`). Location YAML overrides per key; there is no
  third level of overrides.
- The existing `config.py` / `prompt_overrides` dicts and the hardcoded workflow shell
  are the migration sources: every value they contain must be representable in the
  YAML, or the schema is wrong and gets fixed before implementation continues.
- Secrets never enter the YAML; model API keys and AWS credentials stay in environment
  variables exactly as today.

### 3.3 The runner CLI

One entry point, used identically locally (Docker image, per README) and in CI:

```
python -m pipeline <location> scrape      # emit new (not-yet-processed) links
python -m pipeline <location> download    # download new content into the run dir
python -m pipeline <location> prepare     # run the prepare pipeline
python -m pipeline <location> extract     # produce menu JSON per prepared input
python -m pipeline <location> publish     # write data/, mark links processed
python -m pipeline <location> all         # the whole pipeline (local runs, act)
python -m pipeline <location> migrate-state  # one-time, see section 5
```

Behavioral requirements:

- **State check placement.** `scrape` filters discovered links against DynamoDB
  (`link_exists`) and emits only unprocessed ones. `publish` marks a link processed
  (`add_link`, TTL from config) only after its menu JSON has been written and
  validated. A failed extraction never marks a link processed — this preserves today's
  retry semantics where a failed PDF page is retried next run.
- **Manifest.** Each run writes a manifest JSON (run id, location, links discovered,
  links new, files downloaded, files prepared, extraction results, links marked) into
  the run directory. CI uploads it as an artifact; it is never committed and never
  written to DynamoDB (decision 3).
- **Idempotence.** Re-running any stage with the same inputs produces the same
  outputs; `all` on a location with no new links is a fast no-op with exit code 0.
- **Exit codes.** 0 success / nothing to do; 1 processing failure; 2 configuration
  error; 3 state-backend unavailable (so CI can distinguish "config bug" from "AWS
  down" from "extraction failed").
- **No workflow-specific logic in the runner.** Matrix building, artifact upload, and
  PR creation stay in the workflow; the runner communicates through files (manifest,
  output JSONs) and stdout.

### 3.4 Absorbing `DefaultMealChat`

`locations/.shared/DefaultMealChat.py` is moved into `pipeline/stages/extract.py` and
simplified, not redesigned:

- Constructor kwargs come from the validated location config instead of the
  `config.py` / `prompt_overrides` pair.
- The `{MC_TODAY}` / `{MC_WEEKSTART}` templating, weekend-rolls-to-next-week logic,
  and `addCurrentDate` / `addCurrentWeekdays` behavior are preserved verbatim (the
  prompt regression tests depend on it).
- The current OpenAI-compatible transport is preserved: both the `openai` and
  `google` model namespaces use `https://router.eu.requesty.ai/v1` with the
  `CHAT_API_KEY` environment variable. The namespace selects the model name, not
  a direct provider endpoint; adding providers is out of scope.
- The `sed -n '/^\s*{$/,$p'` JSON-carving currently done in workflow shell becomes a
  tested `extract_json_object()` function in the runner.

### 3.5 Format variants: handling locations that switch menu formats

**Problem.** Some locations change how the menu is published over time. The known
case is Le Casino: the menu was a PDF link, then became an HTML page (the current
`scra.py` follows `Speiseplan` links, downloads the pages, and reduces them to text),
then PDF links came back (the recent `scraped_done.txt` entries are PDF URLs again).
The rework must make "the website changed format again" a **config-only event** —
ideally reordering one list — without reintroducing per-format workflow copies.

**Design: an ordered `formats:` list per location.** The `scrape:`/`prepare:`/
`extract:` blocks from section 3.2 become the *default variant*. A location with
format history declares additional variants under `formats:`, each a complete,
self-contained variant of the same three blocks:

```yaml
# locations/lecasino/location.yaml (illustrative)
name: LVB - Le Casino
website:
  url: https://www.l.de/gruppe/.../le-casino/
scrape:            # default variant = the currently active format
  type: scrapy
  spider:
    allowed_domains: [www.l.de, files.l.de]
    link_xpath: '//a[contains(@href,".pdf")]/@href'
download:
  formats: [pdf]
prepare:
  - pdfseparate: {}
  - pdftoppm: { resolution: 150, format: png, singlefile: true }
extract:
  type: vision
  input_file: image.png
  model: { provider: openai, vision_model: gpt-4o-2024-08-06 }
formats:           # known fallbacks, tried after the default, in order
  - name: html-page
    scrape:
      type: scrapy
      spider:
        allowed_domains: [www.l.de]
        link_xpath: '//a[contains(text(),"Speiseplan")]/@href'
        follow: true            # fetch each linked page instead of a file
    download:
      formats: [html]
    prepare:
      - html_to_text: {}        # the cleaned_*.html text reduction from today's scra.py
    extract:
      type: text
      prompt_prefix: 'The input only includes day offers and no week offers! ...'
```

**Selection semantics (deliberately boring):**

1. Variants are tried strictly in order: default first, then `formats:` entries top to
   bottom.
2. A variant *wins* when its discovery succeeds, defined as: the scrape stage
   completes without error **and** yields at least one link that DynamoDB does not
   already know (i.e. new, processable content exists). A variant that discovers only
   already-processed links is a valid win — it means "format still active, nothing
   new", and the run ends as a no-op like today.
3. A variant *loses* when the scrape stage errors or discovers zero links at all —
   treating "zero links" as failure matches the current spiders, which already exit
   non-zero / `CloseSpider` in that case. The runner then tries the next variant.
4. If every variant loses, the run fails (exit 1) and the workflow alerts exactly as a
   broken spider does today. There is no silent skipping.
5. Only the winning variant's prepare/extract pipeline runs. Variants never mix
   stages, never run in parallel, and never merge results.
6. The winning variant's name is recorded in the run manifest (section 3.3) so the
   history of format switches is visible in CI artifacts.

**Why this stays maintainable (the complexity budget):**

- **No detection logic.** The runner contains no format sniffing; "try in order, first
  success wins" is ~20 lines in the scrape stage and is the only new control flow in
  the whole rework.
- **Variants reuse the same stage machinery.** A variant is just another config for
  the same `scrape`/`prepare`/`extract` stages — no variant-specific code paths.
  `html_to_text` becomes one more named preparer next to `pdfseparate`/`pdftoppm`,
  implemented once in `pipeline/stages/prepare.py` and unit-tested like the others.
- **The common case pays nothing.** Locations with a single format (six of seven
  today) have no `formats:` key; the loader treats the default variant as a one-element
  list internally.
- **Format switches become trivial config edits.** When Le Casino flips again, the
  change is reordering `formats:` (or promoting a variant to the default) in one YAML
  file — no new workflow, no new script, no code review of Python.
- **Dead variants are pruned.** A variant that has lost for a documented period
  (suggestion: two scheduled cycles after a switch is confirmed) should be removed
  from the YAML in the same PR that confirms the switch, so the list never grows into
  an archaeology of every historical format.

**Honest limits.** Discovery-level fallback cannot detect a *silent* format change
(e.g. the page keeps offering links but the menu content moved elsewhere) — that
failure class already exists today and is caught by extraction/prompt regression
tests, not by scraping. Cross-format deduplication relies on links being format
specific (a PDF URL and an HTML page URL are different `link` values); if a location
ever serves two active formats for the *same* menu period simultaneously, the
operator must disable one variant — the runner deliberately does not arbitrate that.

### 3.6 The single workflow

`.github/workflows/location.yaml` replaces the seven per-location files:

- Trigger: `workflow_dispatch` with a `location` input (choice of the seven + `all`),
  plus one `schedule` entry per location. If GitHub's lack of parameterized cron makes
  seven thin caller workflows unavoidable, generate them from a template with a single
  reusable workflow containing all logic — the logic exists exactly once either way.
  Decide during implementation; prefer the matrix/reusable-workflow option with the
  fewest files.
- Jobs mirror the runner stages: `scrape+download` (builds the file matrix from the
  manifest instead of inline jq), `process` (matrix over prepared inputs, runs
  `prepare` + `extract`), `publish` (runs `publish`, opens the data PR with the
  existing `peter-evans/create-pull-request` + app-token mechanism, unchanged).
- Container image references stay as they are (decision 5); the new workflow uses the
  same pinned image as the current workflows unless a proven dependency gap forces the
  minimal image change procedure from decision 5.
- The `concurrency: singlethread` and `max-parallel: 1` semantics of current locations
  are preserved per location via a concurrency group keyed on the location name.

## 4. Migration of processed-content state to DynamoDB

Goal: after cutover, `scraped_done.txt` no longer exists and every location uses the
`lunchdeal` table for the processed check.

1. **Inventory.** For each of the seven locations, dump `data/<loc>/scraped_done.txt`
   (where present) and record counts in the migration section of the PR description.
   Recheck against the live table immediately before writing (see the snapshot warning
   at the top of this document).
2. **Backfill.** For every line in every `scraped_done.txt`, call the equivalent of
   `add_link(link, ttl_weeks=8)` (decision 4) via `pipeline <loc> migrate-state`
   (dry-run by default; `--apply` to write). The command skips entries already present
   and unexpired in the table, and logs a per-location summary (added / skipped /
   failed). Failures abort the migration for that location, not the others.
3. **Dual-read transition (one release).** For one scheduled cycle, the runner's state
   check reads DynamoDB **and** still tolerates the presence of `scraped_done.txt`
   (union of both) while writes go only to DynamoDB. This makes a botched backfill
   recoverable without reprocessing everything.
4. **Cleanup.** After one successful scheduled cycle per location, delete the
   `scraped_done.txt` files and the dual-read code path in the same PR that switches
   the workflows over (section 6). The historical menu JSONs in `data/<loc>/` are
   untouched (decision 2).

Note: `dynamodb_link_validator.py` currently also writes `created_at` / `expires_at`
attributes. Under decision 3 the runner's state module writes only `link` and
`timestamp`; the helper is trimmed accordingly during the move into
`pipeline/state/dynamodb.py`. Existing extra attributes on old items are harmless and
expire with their TTL.

## 5. Removals (with reference checks)

Each removal is a separate commit in the rework branch, preceded by a `rg` reference
check whose output is pasted into the commit message:

1. `data/milchbarpinguin/` (decision 1) plus any website entry that renders it
   (`site/` data listing) and any workflow/test references.
2. `locations/*/process_textractor_result.py` (lecasino, leos, ratskeller), the
   Textract/`boto3`-textract usage they support, and any Textract mentions in
   README/docs (decision 6). Confirm no workflow step calls them first.
3. `locations/*/process_chatgpt.py` shims and `locations/*/config.py` once the
   location YAML and runner cover them (kept until cutover to keep old workflows
   functional during the transition).
4. `locations/*/scra.py` once spider definitions live in `location.yaml` and the
   runner's scrapy stage generates/executes them.
5. The seven per-location workflow files after the parameterized workflow has run
   green for every location.

## 6. Implementation phases and verification

Each phase is independently mergeable; phases 1–3 do not change production behavior.

| Phase | Deliverable | Verification gate |
|-------|-------------|-------------------|
| 1. Config foundation | `pipeline/config.py`, `pipeline/defaults.yaml`, schema, all seven `location.yaml` files (lecasino with both PDF and HTML variants) | Unit tests: every YAML validates; rendered effective config equals today's `config.py`+`prompt_overrides`+workflow shell behavior, diffed per location; variant selection logic unit-tested for win/loss/no-new-content/exhausted cases |
| 2. Runner core | `pipeline/` stages + state module + manifest, `DefaultMealChat` absorbed | Unit tests per stage with mocked HTTP/model/DynamoDB; `python -m unittest` in `tests/<location>/` passes against YAML-driven config for all seven locations |
| 3. Local end-to-end | `all` mode | Docker image run (per README) of `all` for 2 representative locations (one text: augustiner; one vision+PDF: ratskeller) against a stubbed model endpoint produces byte-comparable menu JSON to the current scripts on the same input |
| 4. State migration | `migrate-state` command, backfill executed, dual-read enabled | Dry-run report reviewed; post-`--apply` table sample-checked; one scheduled cycle per location green with dual-read |
| 5. Workflow cutover | `location.yaml` workflow; seven old workflows and `scraped_done.txt` deleted; dual-read removed | `act` dry-run per README; one real scheduled run per location green; data PR contents match expectations |
| 6. Removals & docs | milchbarpinguin, Textract helpers/deps, stale docs removed; README updated | Reference-check output in commit messages; site build green without the removed location; full test suite green |

## 7. Risks and mitigations

- **Behavior drift in prompts/templating.** The prompt regression tests under
  `tests/<location>/` are the contract; phase 2's gate requires them green against the
  YAML-driven path before any workflow change.
- **DynamoDB backfill mistakes.** Dry-run default, per-location isolation, dual-read
  transition, and the eight-week TTL (which self-heals any missed entry after expiry)
  bound the blast radius.
- **Schedule loss during cutover.** The phase-5 PR must demonstrate (in its
  description) the mapping from each old cron to the new trigger before the old
  workflows are deleted.
- **Image dependency gap.** If the runner needs a package missing from the pinned
  image (e.g. a YAML parser), follow decision 5's minimal-image-change procedure; do
  not work around it in shell.
- **Schema overreach.** The YAML schema must be proven against the seven existing
  locations in phase 1 before any runner code is written; if a current behavior cannot
  be expressed, fix the schema, not the behavior.

## 8. Open questions to resolve during implementation (not design)

1. Single matrix workflow vs. seven generated callers + one reusable workflow
   (section 3.6) — pick by file count and GitHub cron constraints.
2. Whether the scrapy stage executes spiders in-process via the Scrapy API or keeps
   shelling out to `scrapy runspider` with a generated spider file — pick by test
   simplicity.
3. Exact name and placement of the runner package (`pipeline/` vs `tools/runner/`) —
   cosmetic, decide in phase 1.
