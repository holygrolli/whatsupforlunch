# whatsupforlunch

Are you also annoyed about the efforts to look up where to go for your (business) lunch? Checking several websites to see what's the menu of the day takes time. And because I hate wasting time (and like to automate things learning new tech) I created this tool.

This is a monorepo containing:

* workflows to scrape restaurants' websites for daily or weekly lunch offers
* configs for each restaurant, how to parse the menu and extract meals and prices
* a small React website which presents you the daily menu

## How it works

Each supported restaurant is described by a single `locations/<name>/location.yaml`
covering the website target, the scrape job, the extraction pipeline, the prompt,
the model, output naming, and the TTL override. A small Python runner package
(`pipeline/`) executes the stages `scrape -> download -> prepare -> extract ->
publish` driven entirely by that YAML plus shared defaults (`pipeline/defaults.yaml`).

Scraping produces some text, a PDF, or an image containing the menu schedule for a
week. Text and PDF pages are sent to an OpenAI-compatible model (text extraction);
images are sent to a vision model. The model transforms the data into the menu JSON
consumed by the website. Processed-content state lives in the DynamoDB `lunchdeal`
table (a URL plus a TTL), so re-running a location only processes new content.

Run the whole pipeline for one location locally:

```
python -m pipeline <location> all
```

or a single stage (`scrape`, `download`, `prepare`, `extract`, `publish`). Use
`--no-state` to disable the DynamoDB check for local testing. A one-time
`python -m pipeline <location> migrate-state` backfills the old `scraped_done.txt`
entries into DynamoDB (dry-run by default, `--apply` to write).

## How to contribute

Please raise an issue or even create a pull request with any improvements or even a new location.

To develop and debug single workflow steps you should use the project's Docker image and provide you personal AWS credentials and OpenAI API key.

```
docker run --rm -it -v $PWD:/data -w /data -v $PWD/.aws.config:/root/.aws/config --env-file .openai ghcr.io/holygrolli/whatsupforlunch:main bash
```

Your `.aws.config` should be a typical AWS profile config looking like

```
[default]
aws_access_key_id = 
aws_secret_access_key = 
region = eu-central-1
```

The OpenAI API key is provided as environment variable inside `.openai` like this:
```
CHAT_API_KEY=
```

To run a full GitHub workflow you can use [`act`](https://github.com/nektos/act) like this:
```
act --pull=false -W .github/workflows/ratskeller.yaml --artifact-server-path=artifacts --secret-file .aws.creds -e event_local.json -n workflow_dispatch
```
The file `.aws.creds` should (again) contain the required environment variables for AWS and OpenAI:
```
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=eu-central-1
CHAT_API_KEY=
```

## Testing

For testing the prompt compared to a previous state just use the same Docker image and change to `tests/LOCATION` and execute `python -m unittest`