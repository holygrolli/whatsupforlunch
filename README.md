# whatsupforlunch

Are you also annoyed about the efforts to look up where to go for your (business) lunch? Checking several websites to see what's the menu of the day takes time. And because I hate wasting time (and like to automate things learning new tech) I created this tool.

This is a monorepo containing:

* workflows to scrape restaurants' websites for daily or weekly lunch offers
* configs for each restaurant, how to parse the menu and extract meals and prices
* a small React website which presents you the daily menu

## How it works

Each restaurant has a config inside `locations` directory. All restaurants have a `scra.py` file defining how to scrape the website. This mostly results in some text, a PDF or an image containing the menu schedule for a week. Depending on the source format, e.g. an image, is then processed by [AWS Textract](https://aws.amazon.com/textract/). This textual meal schedule is then sent to ChatGPT with a `prompt.txt` to transform the data finally into a JSON.

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
OPENAI_API_KEY=
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
OPENAI_API_KEY=
```