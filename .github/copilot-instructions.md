# Copilot instructions for esign-forms

Python library + CLI (`esign-forms`, published to PyPI) that renders a Jinja2 HTML template into
a PDF with **fillable AcroForm fields** (via WeasyPrint's native form-control rendering,
`pdf_forms=True`), sends it to DocuSign, and reads filled/signed values back out. The main
consumer is a Go service that installs the CLI into its rock with `uv tool install` and calls it
as a subprocess, so the **CLI's JSON contract and exit codes are a public API**.

## Build, test, run

Use **uv** (pinned via `mise.toml` together with Python 3.13 for development). Dependencies are locked in
`uv.lock`; add/remove them with `uv add` / `uv remove`, never by hand-editing the lock.

```bash
uv sync                    # create .venv, install deps + dev tools (+ the worker extra)
uv run pytest              # run all tests
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy                # strict mode, configured in pyproject.toml
uv build                   # sdist + wheel
```

Run a single test file or test (pytest node ids):

```bash
uv run pytest tests/form/test_form_reader.py
uv run pytest tests/test_form_generator.py::test_generates_pdf_with_expected_fillable_fields
```

Console scripts: `esign-forms` (`esign_forms.cli:main`) and `esign-forms-worker`
(`esign_forms._worker_entry:main`, which prints an install hint when the `worker` extra is
missing).

CI (`.github/workflows/ci.yml`) runs pytest on Python 3.12 and 3.13 plus ruff + mypy. Keep them
green. `.github/workflows/release.yml` publishes on `v*` tags (details under "Releasing").

## Toolchain constraints

- **Python ≥ 3.12** (`requires-python`; ruff/mypy target 3.12). Consumers' rocks use the
  distro `python3` (24.04 = 3.12), so don't use 3.13-only syntax or stdlib APIs.
- **WeasyPrint needs system Pango/HarfBuzz** (`libpango-1.0-0 libpangoft2-1.0-0
  libharfbuzz-subset0` on Ubuntu; `brew install pango` on macOS). On macOS `uv run` strips
  `DYLD_*`, so `render._ensure_macos_library_path()` defaults `DYLD_FALLBACK_LIBRARY_PATH` to
  Homebrew's lib dir right before WeasyPrint is first imported (ctypes `find_library` reads it at
  call time). `render.py` imports
  WeasyPrint lazily so the rest of the package imports without those libs.
- **`docusign-esign`** provides the DocuSign SDK models/clients for the `docusign` package.
- **`temporalio`** is an **optional extra** (`esign-forms[worker]`); the `dev` group pulls it in so
  tests and mypy cover `temporal`. Nothing outside `esign_forms.temporal` / `_worker_entry` may
  import it. The time-skipping test server is downloaded on first test run.

## Architecture

Two inverse pipelines, both fronted by `FormGenerator` (the main public entry point):

```
generate:  FormData ─▶ TemplateEngine (Jinja2) ─▶ HTML
                    ─▶ HtmlToPdfRenderer (WeasyPrint) ─▶ PDF + AcroForm
                    ─▶ AcroFormPostProcessor (pypdf) ─▶ bytes

read:      bytes/path/stream ─▶ FormReader (pypdf) ─▶ dict[str, str]
```

Package `esign_forms` (`src/` layout):
- `generator.FormGenerator` — facade; `generate(template, data, expected, required)` and
  `read_values(...)`.
- `template.TemplateEngine` — **no bundled templates.** `template` is a `Path`/`PathLike`
  (loaded with a `FileSystemLoader` on its directory, so includes work; the renderer's `base_url`
  is that directory so relative CSS/images resolve) or a `str` of template text
  (`from_string`, no base URL). Autoescape on; undefined renders empty.
- `cli` — the `esign-forms` CLI (see below).
- `render.HtmlToPdfRenderer` — WeasyPrint render; registers the bundled font.
- `form.AcroFormPostProcessor` — rebuilds the field tree, validates names, sets
  `NeedAppearances`, rejects duplicates, sets the Required flag.
- `form.FormReader` — extracts field values from a filled PDF.
- `form.FieldNaming` — the field-name convention + validation.
- `form._acroform` — shared pypdf field-tree walking helpers (internal).
- `model.FormData` — immutable holder (builder or plain mapping) for template values.

`examples/contract.html` is the sample template and the test fixture (`tests.conftest.EXAMPLE_TEMPLATE`).

The fillable regions are **not** placed by anchor text or coordinates: they are ordinary HTML
form controls (`<input>`, `<textarea>`, checkbox, radio, `<select>`) in the template, whose
`name` attribute becomes the AcroForm field's fully-qualified name.

## Non-obvious conventions & gotchas

- **WeasyPrint writes dotted names flat.** A control named `party.name` comes out as one root
  field with `/T (party.name)`. `AcroFormPostProcessor._build_hierarchy` rewrites these into a
  spec-compliant tree (non-terminal `party` → terminal `name`), so `party` exists as a parent node
  with no `/FT`. Anything walking fields should use `form._acroform.walk_fields`, which yields
  fully-qualified names and a `terminal` flag.
- **WeasyPrint lists radio widgets twice** — under the group's `/Kids` *and* as root `/Fields`
  entries, each with its own `/T`. The post-processor drops the duplicate root entries and strips
  `/T`/`/TU`/`/FT` from the widgets; otherwise duplicate detection would fire. Radio on-states are
  indices (`/0`, `/1`) into the group's `/Opt`, which the reader maps back to export values.
- **A font must be registered**: `HtmlToPdfRenderer` injects an `@font-face` for the bundled
  `resources/fonts/OpenSans-Regular.ttf` (Open Sans, SIL OFL) under the family `EsignFormsFont`
  (`render.FONT_FAMILY`); templates must use that family.
- **Field names must satisfy `FieldNaming`**: start with a letter; only letters, digits, `.`,
  `_`, `-` (checked with `re.fullmatch`). Invalid names raise `ValueError`.
- **Signature boxes use DocuSign's `transformPdfFields` naming.** WeasyPrint can't emit a PDF
  `/Sig` field, so a signature is created by *name*: DocuSign converts a form field whose name
  **contains** `DocusignSignHere` (e.g. `DocusignSignHere1`, via `FieldNaming.sign_here(1)`) into
  a SignHere tab when the envelope is sent with `transform_pdf_fields="true"`. The trailing index
  only keeps names unique — it does **not** route to a signer: converted tabs are assigned to
  `assign_tabs_to_recipient_id` (`EnvelopeFactory` sets `"1"`). The template's signature box is
  `<input name="DocusignSignHere1" id="sig.signature" />`. Single-signer only. (The backslash
  `\s1\` form is **not** a `transformPdfFields` convention — it does nothing.)
- **Checkbox values are read from the raw `/V` name**, compared to the widget's non-`/Off`
  on-appearance state, and normalized to `"true"`/`"false"`. Don't switch to `/Opt`-based
  export-value lookups — some producers write placeholder `/Opt` arrays.
- **`FormReader` returns terminal fields only** and returns an **empty dict** (never
  raises) for a PDF with no AcroForm. Unloadable input raises `ReadError`.
- **Error messages are asserted by tests** (e.g. `Expected form fields are missing: [a, b]` —
  names sorted). Keep them stable.
- pypdf has no public API to register a new indirect object on a writer; the post-processor uses
  `PdfWriter._add_object` deliberately.

## Signatures / DocuSign

`esign_forms.docusign` sends the generated PDF to DocuSign for signature via the official
`docusign-esign` SDK, using **JWT Grant** auth and tab **auto-detection**
(`Document.transform_pdf_fields="true"` — no manual tab placement/coordinates).

- **Pure / unit-tested (no network):** `EnvelopeFactory` (builds the SDK `EnvelopeDefinition`
  from a `SendRequest`) and `DocuSignSender` (facade; tested with a fake `DocuSignClient`
  Protocol implementation).
- **Network I/O, integration-tested only:** `JwtAuthenticator` (JWT auth, resolves the account's
  REST base URI via the userinfo endpoint, sets `ApiClient.host` to `<base_uri>/restapi`) and
  `EsignDocuSignClient` (calls `EnvelopesApi.create_envelope`). Exercised by
  `tests/docusign/test_docusign_live.py`, skipped unless `DOCUSIGN_LIVE_TEST=true` and the other
  `DOCUSIGN_*` env vars are set (see its docstring). `scripts/live_send.py` is a manual sender
  (reads `private_key.pem` next to itself).
- `DocuSignConfig`, `Signer`, `SendRequest` are frozen dataclasses that validate in
  `__post_init__` (blank strings → `ValueError`); the private key is excluded from `repr`.
  `DocuSignConfig.from_env(env)` reads the `DOCUSIGN_*` variables (`DOCUSIGN_PRIVATE_KEY` inline
  wins over `DOCUSIGN_PRIVATE_KEY_PATH`) and raises `ValueError` when something is missing; the
  CLI and the Temporal activities both use it.
- **Required fields, in both places:** `FormGenerator.generate(..., expected_field_names,
  required_field_names)` sets the AcroForm Required flag; because `EnvelopeFactory` always sets
  `transform_pdf_fields="true"`, DocuSign's auto-converted tabs inherit it.
- **Multi-signer caveat:** auto-converted tabs are all assigned to one recipient — field names do
  **not** route tabs to individual signers. Single-signer envelopes are the supported path.
- Out of scope by design: non-JWT auth flows, explicit per-tab placement, embedded signing
  (recipient views), DocuSign Connect webhooks for *sending*, envelope status polling.

## Receiving signed docs (`docusign.webhook`)

`esign_forms.docusign.webhook` parses the **inbound** DocuSign Connect notification back
into form values — the inverse of the send pipeline.

- `ConnectWebhookParser.parse(bytes | str)` → `SignedEnvelope(envelope_id, status, documents)`;
  each `SignedDocument` carries `pdf_bytes` + parsed `fields`. It reuses
  `form.FormReader`, so all the reader's conventions apply to `SignedDocument.fields`.
- **Only the JSON eSignature Connect format is parsed.** The base64 PDF lives at
  `data.envelopeSummary.envelopeDocuments[].PDFBytes` — note **`PDFBytes`**, *not*
  `documentBase64` as in the SDK's `EnvelopeDocument` model. Parsed with stdlib `json`.
- **Parse-regardless-of-status:** a notification without documents parses into an empty
  `documents` tuple rather than raising; only malformed JSON / a missing `data` object / invalid
  base64 raise `WebhookParseError` (a `ValueError`). The completion certificate ("summary")
  document has no form and yields empty fields.
- `ConnectHmacVerifier.verify/verify_any` is a pure HMAC-SHA256 `hmac.compare_digest` check of
  the **raw** request body against the Connect HMAC secret (`X-DocuSign-Signature-N` header).
  Verify before parsing; never re-serialize the body first.
- Out of scope: legacy XML Connect payloads, fetching documents from the API when the webhook
  omits them, and the HTTP endpoint/routing itself (caller's responsibility).

## CLI (`cli.py`)

`esign-forms {generate,send,send-pdf,read,parse-webhook}` — argparse, no extra deps. The Go
consumer depends on this contract, so treat changes as breaking and document them in the README:

- File args (`--template`, `--input`, `--pdf`, `--output`) accept `-` for stdin/stdout; **at
  most one input** may be `-`. A template from stdin is template text (no includes/base URL).
- JSON keys are **camelCase**; unknown keys are rejected (`_check_keys`). Inputs:
  `{data, expectedFields, requiredFields}` for generation, `{documentName, emailSubject,
  signers:[{name,email,routingOrder}]}` for sending (`send` takes both).
- Success output goes to stdout (PDF bytes, or one JSON line). Failures write
  `{"error": {"type", "message"}}` to stderr with exit codes `1 internal`, `2 invalid_input`
  (argparse via `_Parser.error`, bad JSON/template/PDF, `ValueError`, `PostProcessError`,
  `ReadError`, `OSError`), `3 docusign`, `4 hmac`, `5 render`.
- `parse-webhook` requires `DOCUSIGN_CONNECT_HMAC_SECRET` (comma-separated secrets allowed) plus
  `--signature` values, or `--no-verify`. `--pdf-dir` writes `<documentId>.pdf` (sanitized)
  and adds `pdfPath`.
- `main(argv, *, stdin, stdout, stderr, env) -> int` is fully injectable. Tests replace the
  module-level `cli.sender_factory` to avoid network I/O (`tests/test_cli.py`).

## Temporal worker (`temporal`, optional `[worker]` extra)

`esign_forms.temporal` wraps the library as a Temporal worker. `temporal/__init__.py` raises a
helpful `ImportError` if `temporalio` isn't installed. There is **no rock** in this repo anymore.

- `FormSigningWorkflow.generate_and_send(FormSigningRequest)` → envelope id (workflow type name
  `FormSigningWorkflow`). It runs two activities from `FormActivities`: `generate_pdf` (wraps
  `FormGenerator`, loading `request.template_path` from the worker's filesystem) then
  `send_to_docusign` (wraps `DocuSignSender`, config via `DocuSignConfig.from_env`), each with a
  2-minute start-to-close timeout and max 3 attempts. PDF bytes pass between them as a top-level
  `bytes` payload through workflow history (~2 MB limit).
- DTOs are frozen dataclasses (`FormSigningRequest`, `SignerInfo`) handled by Temporal's default
  JSON converter (snake_case keys); `__post_init__` normalizes `None` collections.
- **Workflow sandbox:** importing `workflow.py` in the sandbox also runs the parent packages'
  `__init__`, which pull in pypdf/Jinja2/DocuSign (pypdf touches `shutil.which`, which the sandbox
  forbids). Always register the workflow with `workflow_runner=WORKFLOW_RUNNER` (from
  `temporal.workflow`), which passes those modules through.
- Activities are **synchronous**, so the worker needs an `activity_executor` (`ThreadPoolExecutor`).
- `TemporalWorkerConfig.from_env(Mapping)` reads `TEMPORAL_HOST`/`_NAMESPACE`/`_QUEUE`/
  `_TLS_ROOT_CAS` (queue required). `worker.main` connects (TLS via
  `TLSConfig(server_root_ca_cert=...)`), optionally serves Prometheus `/metrics` on
  `TEMPORAL_PROMETHEUS_PORT`, and shuts down gracefully on SIGTERM/SIGINT.

## Releasing

Bump `project.version`, then tag `vX.Y.Z` and push the tag. `release.yml`:
1. Runs the tests and checks that the tag matches `uv version --short`.
2. Runs `uv build`.
3. Exports `dist/constraints.txt` with `uv export --locked --no-dev --no-hashes --no-emit-project`
   (base deps only, no worker extra).
4. Smoke-tests the wheel via `uv tool install`.
5. Publishes to PyPI with trusted publishing (environment `pypi`).
6. Creates a GitHub Release with the wheel, sdist and `constraints.txt`.

Consumers pin both the version and the constraints file. The sdist includes only `src`, `tests`,
`examples`, README and LICENSE.

## When adding fields

Adding a control to `examples/contract.html` is a cross-file change: update the template, and if
a test asserts the expected field set (`EXPECTED_FIELDS` in `tests/test_form_generator.py`) or
round-trips values (`tests/conftest.py` `fill_sample_fields`, `tests/form/test_form_reader.py`),
update those too.
