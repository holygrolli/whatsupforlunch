# Optional SolveGate Cloudflare WAF integration plan

**Status:** proposed implementation plan for review before rollout.

## 1. Goal and constraints

GitHub-hosted Scrapy runs can receive a Cloudflare challenge instead of the
Augustiner menu page. Add a narrowly scoped, opt-in SolveGate integration so the
existing pipeline continues to work unchanged for locations without the option.
The first enabled location is Augustiner.

SolveGate's documented WAF flow is described in the [API reference](https://solvegate.io/docs),
[Supported Gates](https://solvegate.io/docs/gates), and the
[OpenAPI specification](https://solvegate.io/openapi.json):


1. `POST https://api.solvegate.io/v1/solve` with `gate: "waf"`,
   `sitekey: "waf"`, and the challenged page URL.
2. Authenticate with `Authorization: Bearer $SOLVEGATE_API_KEY`.
3. On a solved live response, decode the JSON in `token`. The WAF payload carries
   clearance `cookies`, `set_cookies`, `headers`, `attributes`, and `cf_rt`.
4. Retry the same target request using the returned cookies and headers in the
   same session/egress context.

Only use this against a property the operator owns or is explicitly authorized
to test. The supplied `sk_test_...` key is a sandbox credential and must remain
an environment/CI secret; it must never be committed or placed in YAML.

## 2. Configuration shape

Add an optional `scrape.challenge` block. Its absence means no solver code is
loaded and current Scrapy behavior is unchanged.

```yaml
scrape:
  type: scrapy
  challenge:
    provider: solvegate
    gate: waf
    sitekey: waf
    api_key_env: SOLVEGATE_API_KEY
    max_attempts: 1
```

Validation rules:

- `provider` is currently only `solvegate`.
- `gate` is currently only `waf`; Turnstile widget support is deliberately not
  included because this target presents a full-page WAF challenge.
- `sitekey` defaults to `waf`, but is explicit in Augustiner's config to make
  the API contract visible.
- `api_key_env` defaults to `SOLVEGATE_API_KEY` and must name an environment
  variable, never contain a key value.
- `max_attempts` defaults to `1` and must be a positive integer. A run makes at
  most one solve/retry per page to prevent loops and accidental repeated billing.

Augustiner gets this block first. Other locations remain opt-in and are not
changed by the implementation.

## 3. Implementation design

### 3.1 Small lazy SolveGate client

Create `pipeline/solvegate.py` with a standard-library HTTP client rather than
making the normal pipeline depend on the optional SDK. It will:

- read the API key only when a configured challenge is actually encountered;
- send JSON and an idempotency key for safe transport retries;
- enforce a bounded timeout;
- reject non-2xx/error envelopes with a `SolveGateError` that does not print the
  key or returned token;
- require `status == "solved"` and a non-empty token;
- decode a WAF token payload and normalize cookies from both `cookies` mappings
  and `set_cookies` strings;
- return only the cookies and safe response headers needed by Scrapy.

The client will not treat a sandbox token as real WAF clearance. This is
important for unit testing: the `sk_test_...` key can verify request/response
plumbing, while a mocked solved WAF payload verifies cookie application. A
sandbox solve should produce a clear error if the code tries to use it against a
real page.

### 3.2 Scrapy retry at the challenge boundary

Extend the generated spider in `pipeline/stages/scrape.py`:

- detect a WAF response when the status is a challenge status (normally 403) or
  the response has `cf-mitigated: challenge`; retain the diagnostic body for
  failures;
- if the configured challenge is present and the request has not exhausted
  `max_attempts`, call the client with the current response URL;
- yield a `scrapy.Request` for that URL with `dont_filter=True`, the normalized
  clearance cookies, and returned headers; mark request metadata so the retry
  cannot recurse indefinitely;
- let the existing XPath parsing run on the retried response;
- if no challenge config exists, preserve today's diagnostics and fail normally;
- if solving or the retry fails, raise `ScrapeError` with actionable context and
  never expose credentials or clearance tokens in CI logs.

The clearance is solved as late as possible and used immediately. It is not
cached in DynamoDB, the manifest, or the repository. Each generated spider
instance owns its attempt state, so concurrent location runs cannot share
cookies.

The initial scope is the Scrapy discovery request only. If a future target
returns a challenge while downloading a linked PDF, that should be a separate
feature using a shared HTTP session; it is not silently folded into this change.

## 4. CI and secret handling

- Declare an optional `SOLVEGATE_API_KEY` secret in the reusable workflow and
  pass it to the scrape job. Existing callers inherit it.
- Add an empty placeholder to the local secret template and document the
  environment variable in `README.md`.
- Do not add the supplied key to source, `location.yaml`, test fixtures, logs, or
  GitHub event files.
- A normal run without the secret is unaffected unless a configured location
  actually receives a challenge; then it fails clearly rather than silently
  scraping a challenge page.

## 5. Tests and verification gates

Add credential-free unit tests that mock the SolveGate HTTP call and Scrapy
response flow:

1. request uses WAF parameters, bearer authentication, timeout, and no secret in
   error text;
2. solved WAF JSON is decoded and `cookies`/`set_cookies` are normalized;
3. challenge response causes exactly one retry with cookies and headers;
4. a normal Augustiner response does not call SolveGate;
5. a second challenge after the retry fails without another solve;
6. absent key/config produces a precise `ScrapeError` only when a challenge is
   encountered;
7. all seven location files still validate and only Augustiner has the opt-in
   block.

Run the offline pipeline/workflow tests. Optionally run a small live smoke test
with `SOLVEGATE_API_KEY` supplied from the environment, but do not point a
sandbox key at a production challenge and do not make live API calls part of the
unit-test suite. Before rollout, confirm the Augustiner page is an authorized
SolveGate target and run one GitHub Actions job with the secret configured.

## 6. Rollout and rollback

1. Review/fine-tune this plan.
2. Implement the client, config validation, Scrapy retry, tests, Augustiner
   config, workflow secret plumbing, and docs.
3. Run offline tests and inspect that no secret is tracked.
4. Enable the GitHub secret and observe one manual Augustiner run.
5. If SolveGate is unavailable or unsuitable, remove the `challenge` block from
   Augustiner's YAML; the client remains inert and all other locations retain
   the old behavior.

Success means a normal Augustiner scrape is unchanged, an authorized WAF
challenge gets one bounded SolveGate-assisted retry, and failures remain
visible/retryable rather than marking any menu link processed.
