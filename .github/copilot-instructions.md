# Copilot instructions for contract-generator

Python library that renders a Jinja2 HTML contract into a PDF with **fillable AcroForm fields**
(via WeasyPrint's native form-control rendering, `pdf_forms=True`) and reads the filled values
back out. The output is meant to be handed off to an e-signature service such as DocuSign.

## Build, test, run

Use **uv** (pinned via `mise.toml` together with Python 3.13). Dependencies are locked in
`uv.lock`; add/remove them with `uv add` / `uv remove`, never by hand-editing the lock.

```bash
uv sync                    # create .venv, install deps + dev tools
uv run pytest              # run all tests
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy                # strict mode, configured in pyproject.toml
uv build                   # sdist + wheel
```

Run a single test file or test (pytest node ids):

```bash
uv run pytest tests/form/test_form_reader.py
uv run pytest tests/test_contract_generator.py::test_generates_pdf_with_expected_fillable_fields
```

The console script `contract-generator-worker` (`contract_generator.temporal.worker:main`) is the
Temporal worker entry point. `rockcraft pack` builds the OCI rock around it.

CI (`.github/workflows/ci.yml`) runs pytest plus ruff + mypy. Keep all three green.

## Toolchain constraints

- **Python ≥ 3.13** (`requires-python`). Modern syntax (`X | Y`, `match`, PEP 695) is fine.
- **WeasyPrint needs system Pango/HarfBuzz** (`libpango-1.0-0 libpangoft2-1.0-0
  libharfbuzz-subset0` on Ubuntu; `brew install pango` on macOS). On macOS `uv run` strips
  `DYLD_*`, so `tests/conftest.py` sets `DYLD_FALLBACK_LIBRARY_PATH` to Homebrew's lib dir before
  WeasyPrint is imported (ctypes `find_library` reads it at call time). `render.py` imports
  WeasyPrint lazily so the rest of the package imports without those libs.
- **`docusign-esign`** provides the DocuSign SDK models/clients for the `docusign` package.
- **`temporalio`** powers the `temporal` worker package; the time-skipping test server is
  downloaded on first test run.

## Architecture

Two inverse pipelines, both fronted by `ContractGenerator` (the main public entry point):

```
generate:  ContractData ─▶ ContractTemplateEngine (Jinja2) ─▶ HTML
                        ─▶ HtmlToPdfRenderer (WeasyPrint) ─▶ PDF + AcroForm
                        ─▶ AcroFormPostProcessor (pypdf) ─▶ bytes

read:      bytes/path/stream ─▶ ContractFormReader (pypdf) ─▶ dict[str, str]
```

Package `contract_generator` (`src/` layout):
- `generator.ContractGenerator` — facade; `generate(...)` and `read_values(...)`.
- `template.ContractTemplateEngine` — Jinja2 `PackageLoader` over `resources/templates`, autoescape on.
- `render.HtmlToPdfRenderer` — WeasyPrint render; registers the bundled font.
- `form.AcroFormPostProcessor` — rebuilds the field tree, validates names, sets
  `NeedAppearances`, rejects duplicates, sets the Required flag.
- `form.ContractFormReader` — extracts field values from a filled PDF.
- `form.FieldNaming` — the field-name convention + validation.
- `form._acroform` — shared pypdf field-tree walking helpers (internal).
- `model.ContractData` — immutable holder (builder or plain mapping) for template values.

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
  `resources/fonts/Contract-Regular.ttf` (Open Sans, SIL OFL) under the family `ContractFont`
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
- **`ContractFormReader` returns terminal fields only** and returns an **empty dict** (never
  raises) for a PDF with no AcroForm. Unloadable input raises `ReadError`.
- **Error messages are asserted by tests** (e.g. `Expected form fields are missing: [a, b]` —
  names sorted). Keep them stable.
- pypdf has no public API to register a new indirect object on a writer; the post-processor uses
  `PdfWriter._add_object` deliberately.

## Signatures / DocuSign

`contract_generator.docusign` sends the generated PDF to DocuSign for signature via the official
`docusign-esign` SDK, using **JWT Grant** auth and tab **auto-detection**
(`Document.transform_pdf_fields="true"` — no manual tab placement/coordinates).

- **Pure / unit-tested (no network):** `EnvelopeFactory` (builds the SDK `EnvelopeDefinition`
  from a `SendRequest`) and `DocuSignSender` (facade; tested with a fake `DocuSignClient`
  Protocol implementation).
- **Network I/O, integration-tested only:** `JwtAuthenticator` (JWT auth, resolves the account's
  REST base URI via the userinfo endpoint, sets `ApiClient.host` to `<base_uri>/restapi`) and
  `EsignDocuSignClient` (calls `EnvelopesApi.create_envelope`). Exercised by
  `tests/docusign/test_docusign_live.py`, skipped unless `DOCUSIGN_LIVE_TEST=true` and the other
  `DOCUSIGN_*` env vars are set (see its docstring). `scripts/live_send.py` is a manual sender.
- `DocuSignConfig`, `Signer`, `SendRequest` are frozen dataclasses that validate in
  `__post_init__` (blank strings → `ValueError`); the private key is excluded from `repr`.
- **Required fields, in both places:** `ContractGenerator.generate(..., expected_field_names,
  required_field_names)` sets the AcroForm Required flag; because `EnvelopeFactory` always sets
  `transform_pdf_fields="true"`, DocuSign's auto-converted tabs inherit it.
- **Multi-signer caveat:** auto-converted tabs are all assigned to one recipient — field names do
  **not** route tabs to individual signers. Single-signer envelopes are the supported path.
- Out of scope by design: non-JWT auth flows, explicit per-tab placement, embedded signing
  (recipient views), DocuSign Connect webhooks for *sending*, envelope status polling.

## Receiving signed docs (`docusign.webhook`)

`contract_generator.docusign.webhook` parses the **inbound** DocuSign Connect notification back
into form values — the inverse of the send pipeline.

- `ConnectWebhookParser.parse(bytes | str)` → `SignedEnvelope(envelope_id, status, documents)`;
  each `SignedDocument` carries `pdf_bytes` + parsed `fields`. It reuses
  `form.ContractFormReader`, so all the reader's conventions apply to `SignedDocument.fields`.
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

## Temporal worker & rock (`temporal`)

`contract_generator.temporal` wraps the library as a Temporal worker, packaged as an OCI rock for
the `temporal-worker-k8s` charm (2.0/stable). The workflow takes a template name + parameters,
generates the PDF, then sends it to DocuSign.

- `ContractSigningWorkflow.generate_and_send(ContractSigningRequest)` → envelope id (workflow
  type name `ContractSigningWorkflow`). It runs two activities from `ContractActivities`:
  `generate_pdf` (wraps `ContractGenerator`) then `send_to_docusign` (wraps `DocuSignSender`),
  each with a 2-minute start-to-close timeout and max 3 attempts. PDF bytes pass between them as a
  top-level `bytes` payload through workflow history (~2 MB limit).
- DTOs are frozen dataclasses (`ContractSigningRequest`, `SignerInfo`) handled by Temporal's
  default JSON converter (snake_case keys); `__post_init__` normalizes `None` collections to
  empty ones and copies them.
- **Workflow sandbox:** importing `workflow.py` in the sandbox also runs the parent packages'
  `__init__`, which pull in pypdf/Jinja2/DocuSign (pypdf touches `shutil.which`, which the sandbox
  forbids). Always register the workflow with `workflow_runner=WORKFLOW_RUNNER` (from
  `temporal.workflow`), which passes those modules through.
- Activities are **synchronous** methods, so the worker needs an `activity_executor`
  (`ThreadPoolExecutor`).
- `TemporalWorkerConfig.from_env(Mapping)` reads `TEMPORAL_HOST`/`_NAMESPACE`/`_QUEUE`/
  `_TLS_ROOT_CAS` (queue required; host/namespace defaulted). `ContractActivities` builds
  `DocuSignConfig` from `DOCUSIGN_*` env (`DOCUSIGN_PRIVATE_KEY` inline or
  `DOCUSIGN_PRIVATE_KEY_PATH`); env and the sender factory are injectable for tests.
- `worker.main` connects (TLS via `TLSConfig(server_root_ca_cert=...)`), optionally serves
  Prometheus `/metrics` on `TEMPORAL_PROMETHEUS_PORT` through the Temporal `Runtime` telemetry
  config, and shuts down gracefully on SIGTERM/SIGINT.
- Tests: `test_worker_config.py` (pure env parsing), `test_workflow.py`
  (`WorkflowEnvironment.start_time_skipping()` + fake activities asserting generate→send
  ordering), `test_activities.py` (`generate_pdf` on the bundled template, env → config).
- Rock: `rockcraft.yaml` (`ubuntu@26.04`, distro `python3` + Pango/HarfBuzz stage-packages) runs
  `uv sync --locked --no-dev --no-editable` into `/app/venv` (built at that exact path so
  shebangs stay valid) and injects `rock/start-worker.sh` at `/app/scripts/start-worker.sh` (the
  charm's Pebble command). Bundled templates ship inside the package.
- **Out of scope** (temporal-lib-py extras): candid/google/OIDC auth, encryption codec, Sentry,
  Vault — extension points only.

## When adding fields

Adding a control to `resources/templates/contract.html` is a cross-file change: update the
template, and if a test asserts the expected field set (`EXPECTED_FIELDS` in
`tests/test_contract_generator.py`) or round-trips values (`tests/conftest.py`
`fill_sample_fields`, `tests/form/test_form_reader.py`), update those too.
