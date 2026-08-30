# whatsupforlunch

Are you also annoyed about the efforts to look up where to go for your (business) lunch? Checking several websites to see what's the menu of the day takes time. And because I hate wasting time (and like to automate things learning new tech) I created this tool.

This is a monorepo containing:

* workflows to scrape restaurants' websites for daily or weekly lunch offers
* configs for each restaurant, how to parse the menu and extract meals and prices
* a small React website which presents you the daily menu

## How it works

Each supported restaurant is described by a single `locations/<name>/location.yaml`
covering the website target, scrape job, extraction pipeline, prompt, model, output
naming, and TTL override. The Python runner in `pipeline/` executes the stages
`scrape -> download -> prepare -> extract -> publish` from that configuration.

Processed-content state is kept in the DynamoDB `lunchdeal` table. A state item has
the source URL in `link` and its Unix expiry in `timestamp`; the default expiry is
eight weeks. The runner writes a temporary `manifest.json` alongside its downloaded
and prepared files, so a CI run can be inspected without adding metadata to the
website data or DynamoDB.

Run the whole pipeline for one location locally:

```bash
python -m pipeline <location> all
```

Individual stages are also available (`scrape`, `download`, `prepare`, `extract`,
and `publish`). Use `--no-state` only for an explicit local smoke test; it bypasses
DynamoDB and must not be used for a production run. The `migrate-state` command is a
dry-run by default and backfills the old `data/<location>/scraped_done.txt` entries
when invoked with `--apply` and working AWS credentials:

```bash
python -m pipeline ratskeller migrate-state
python -m pipeline ratskeller migrate-state --apply
```

The seven scheduled locations are orchestrated by the single
`.github/workflows/location.yaml` workflow. A manual dispatch accepts `all` or one
of `augustiner`, `emilundmoritz`, `galeria`, `lecasino`, `leos`, `moritzbastei`, and
`ratskeller`. The workflow keeps a temporary dual-read of legacy marker files during
the state cutover (`--legacy-state`) but writes processed state only to DynamoDB.
After the migration has been applied and one successful cycle has been observed per
location, remove the legacy marker files and the `--legacy-state` arguments together.

## How to contribute

Please raise an issue or even create a pull request with any improvements or even a new location.

To develop and debug a pipeline locally, use the same pinned Docker image as the
location workflow and provide a Requesty.ai API key. AWS credentials are only needed
when you intentionally use the DynamoDB state check or publish state in a non-`act`
run.

```bash
docker run --rm -it \
  -v "$PWD:/data" -w /data \
  -v "$PWD/.aws.config:/root/.aws/config" \
  -e OPENAI_COMPATIBLE_API_KEY="$OPENAI_COMPATIBLE_API_KEY" \
  ghcr.io/holygrolli/whatsupforlunch:sha-9acaed8-2026-08-30 bash
```

The runner needs PyYAML to load `location.yaml`; it is declared in
`docker/Dockerfile`. If your local copy of the pinned image predates this
dependency, rebuild/publish the image with the Docker workflow before enabling a
scheduled run.

For a normal local Docker shell, `.aws.config` can contain a typical AWS profile:

```ini
[default]
aws_access_key_id =
aws_secret_access_key =
region = eu-central-1
```

`OPENAI_COMPATIBLE_API_KEY` is the secret for the OpenAI-compatible model endpoint:

```bash
export OPENAI_COMPATIBLE_API_KEY=...
# or put OPENAI_COMPATIBLE_API_KEY=... in an ignored .openai file and use --env-file .openai
```

## Manual workflow testing with `act`

`event_local.json` is a safe checked-in event template selecting `ratskeller` and
setting the `act` marker. In that mode the workflow uses `--no-state` and skips PR
creation, while still exercising live discovery, preparation, and the Requesty model
call. `act/secrets.example` contains empty placeholders only; never put credentials
in it.

First validate the action graph without starting containers or contacting a website:

```bash
act --pull=false \
  -W .github/workflows/location.yaml \
  -e event_local.json \
  -n workflow_dispatch
```

To run the selected location for real, export the provided key and pass it as an
`act` secret. The empty example file remains useful for the non-API values:

```bash
: "${OPENAI_COMPATIBLE_API_KEY:?export OPENAI_COMPATIBLE_API_KEY first}"
act --pull=false \
  -W .github/workflows/location.yaml \
  --artifact-server-path artifacts \
  --secret-file act/secrets.example \
  --secret OPENAI_COMPATIBLE_API_KEY="$OPENAI_COMPATIBLE_API_KEY" \
  -e event_local.json \
  workflow_dispatch
```

Change `event_local.json`'s `inputs.location` to another supported location for a
second run. Use one location at a time when testing with a real model; `all` can
make seven live discovery/model runs. The run artifacts include the pipeline manifest
and are written below `artifacts/`. The `act` event intentionally bypasses AWS and
PR creation; a GitHub scheduled/manual run without that marker uses DynamoDB and the
normal app-token/create-pull-request publication path.

For a production-like `act` run with AWS state enabled, use a private secret file
containing `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and
`OPENAI_COMPATIBLE_API_KEY`, and remove the `act` field from the event. Do not commit that
file.

## Testing

The offline unit tests do not contact AWS, restaurant websites, or the model:

```bash
python3 -m unittest tests.pipeline.test_config tests.pipeline.test_stages -v
```

The location prompt regression tests are credentialed tests. Run only the location
you want to check, from its test directory, with the provided Requesty key:

```bash
(cd tests/ratskeller && OPENAI_COMPATIBLE_API_KEY="$OPENAI_COMPATIBLE_API_KEY" python -m unittest -v)
```

The same command can be used for the other location directories. These tests write
only their response/usage files under `tests/<location>/`; do not run them as part of
the default credential-free test suite. A configuration error exits with code `2`,
a processing failure with `1`, and an unavailable DynamoDB backend with `3`.
