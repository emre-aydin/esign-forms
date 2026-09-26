# contract-generator

Python library that renders a **Jinja2 HTML contract** into a **PDF with fillable AcroForm
fields**, ready to hand off to an e-signature service such as DocuSign.

Fillable regions are declared as ordinary **HTML form controls** (`<input>`, `<textarea>`,
checkbox, radio, `<select>`) in the template. [WeasyPrint](https://weasyprint.org/) renders them
directly into interactive AcroForm fields (`pdf_forms=True`) — there are no anchor-text
placeholders or coordinate math. [pypdf](https://pypdf.readthedocs.io/) then validates and
normalizes the form.

## Requirements

- **Python 3.13+** and [uv](https://docs.astral.sh/uv/) (`mise install` sets up both from
  `mise.toml`).
- WeasyPrint's system libraries (**Pango**, HarfBuzz):
  - Debian/Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`
  - macOS: `brew install pango`. Outside the test suite (which sets this itself), export
    `DYLD_FALLBACK_LIBRARY_PATH=/opt/homebrew/lib` so WeasyPrint can find the libraries.

## Build & test

```bash
uv sync                                  # create .venv and install deps (incl. dev tools)
uv run pytest                            # run the test suite
uv run pytest tests/test_contract_generator.py::test_generates_pdf_with_expected_fillable_fields
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy                              # strict type check
uv build                                 # build sdist + wheel into dist/
```

## Usage

```python
from pathlib import Path

from contract_generator import ContractData, ContractGenerator

data = (
    ContractData.builder()
    .put("title", "Consulting Services Agreement")
    .put("provider", "Acme Consulting LLC")
    .put("client", "Globex Corporation")
    .put("effectiveDate", "2026-09-13")
    .put("recital", "The Provider agrees to deliver consulting services to the Client.")
    .build()
)  # a plain dict works too: ContractGenerator().generate("contract", {"title": ...})

pdf = ContractGenerator().generate("contract", data)
Path("contract.pdf").write_bytes(pdf)
```

Optionally assert that specific fields exist in the output:

```python
pdf = ContractGenerator().generate("contract", data, {"party.name", "sig.date"})
```

Optionally also mark some of those fields as required (sets the AcroForm Required flag, which
DocuSign auto-detection carries over to the resulting tab — see "DocuSign hand-off" below):

```python
pdf = ContractGenerator().generate(
    "contract", data,
    {"party.name", "sig.date"},   # expected fields
    {"sig.date"},                 # required fields
)
```

Validation failures raise `form.PostProcessError` (e.g.
`Expected form fields are missing: [does.not.exist]`); an invalid field name raises `ValueError`.

## Reading filled values

Once a user has filled in the generated PDF (in Acrobat, a browser, or after a round trip through
a signing service), read the values back by field name — the inverse of `generate`:

```python
values = ContractGenerator().read_values(Path("filled-contract.pdf"))
# values["party.name"] -> "Jane Doe"
# values["agree.terms"] -> "true"
```

`read_values` accepts `bytes`, a path (`str`/`Path`), or a binary stream (read but not closed).
`form.ContractFormReader` implements this directly if you don't need the rest of the facade.

Value conventions:

- Text / textarea / choice fields return the typed value, or `""` if unfilled.
- Checkboxes are normalized to `"true"` / `"false"`.
- Radio groups return the selected option's `value`, or `""` if none is selected.
- Only **terminal** fields are returned — dotted-name parents (e.g. `party` for `party.name`)
  are internal AcroForm hierarchy nodes, not values, and are skipped.
- A PDF with no AcroForm at all (a plain, non-fillable PDF) returns an **empty dict** rather than
  raising. Unreadable input raises `form.ReadError`.

## Pipeline

```
ContractData ─▶ Jinja2 (ContractTemplateEngine) ─▶ HTML
             ─▶ WeasyPrint (HtmlToPdfRenderer, pdf_forms=True) ─▶ PDF + AcroForm
             ─▶ pypdf (AcroFormPostProcessor: hierarchy, validate, NeedAppearances) ─▶ bytes

bytes (filled PDF) ─▶ pypdf (ContractFormReader: walk AcroForm) ─▶ dict[str, str]
```

| Module / class                     | Responsibility                                                   |
|------------------------------------|------------------------------------------------------------------|
| `ContractGenerator`                | Public facade wiring the generate and read pipelines together    |
| `template.ContractTemplateEngine`  | Jinja2 → HTML (autoescaped, templates loaded from the package)   |
| `render.HtmlToPdfRenderer`         | WeasyPrint render with form fields; registers the bundled font   |
| `form.FieldNaming`                 | AcroForm field-name convention + validation                      |
| `form.AcroFormPostProcessor`       | Build field tree, validate, set `NeedAppearances`, reject dupes  |
| `form.ContractFormReader`          | Reads current AcroForm field values from a (filled) PDF          |
| `model.ContractData`               | Immutable holder for dynamic template values                     |

## Authoring templates

Templates live in `src/contract_generator/resources/templates/*.html` and are rendered with
**Jinja2** (autoescaping on; undefined variables render as empty strings). Insert values with
`{{ name }}`.

- **A bundled font is registered** at `resources/fonts/Contract-Regular.ttf` (Open Sans, SIL OFL)
  under the family `ContractFont` (`render.FONT_FAMILY`); templates should use that family so
  output doesn't depend on the host's installed fonts.
- **Give controls explicit dimensions** (`width`/`height`) — the widget rectangle is the
  control's CSS box.
- **The control's `name` attribute becomes the AcroForm field name.** Names must satisfy
  `FieldNaming` (start with a letter; only letters, digits, `.`, `_`, `-`). Dotted names such as
  `party.name` become a hierarchical field (`party` → `name`) whose fully-qualified name is
  `party.name`. WeasyPrint writes the dotted name flat; `AcroFormPostProcessor` rebuilds the
  proper parent/kid tree.

### Control-type support

| HTML control              | AcroForm result                                                                                                      |
|---------------------------|----------------------------------------------------------------------------------------------------------------------|
| `<input type="text">`     | text field                                                                                                           |
| `<textarea>`              | multiline text field                                                                                                 |
| `<input type="checkbox">` | checkbox                                                                                                             |
| `<input type="radio">`    | radio group (one field per `name`, export values from `value`)                                                       |
| `<select>`                | choice field                                                                                                         |
| signature                 | no native control — use a text field named `DocusignSignHere<N>`; DocuSign converts it to a SignHere tab (see below) |

> **Checkbox reading:** `ContractFormReader` decides checked/unchecked by comparing the field's
> raw `/V` name to its on-appearance state instead of trusting `/Opt` export-value lookups, which
> some producers fill with placeholders.

## DocuSign hand-off

Sending a generated PDF to DocuSign for signature is built in (package
`contract_generator.docusign`). It uses the official
[`docusign-esign`](https://pypi.org/project/docusign-esign/) SDK with **JWT Grant** auth (a
service integration; no browser flow) and DocuSign's tab **auto-detection**: the PDF's AcroForm
fields are converted into signing tabs on import, so there's no manual tab placement or coordinate
mapping to maintain.

### One-time DocuSign app setup

1. Create an Integration Key (OAuth client id) in the DocuSign Admin console, of type **JWT**.
2. Generate an RSA keypair for it; keep the private key (PEM) — DocuSign only stores the public key.
3. Grant consent once for the impersonated user by visiting (demo environment):
   `https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=<integration_key>&redirect_uri=<any_registered_uri>`
4. Note the account id (GUID) and the impersonated user id (GUID) from the DocuSign Admin console.

### Sending an envelope

```python
from contract_generator.docusign import DocuSignConfig, DocuSignSender, SendRequest, Signer

config = DocuSignConfig(
    account_id=account_id,                        # DocuSign account id (GUID)
    oauth_base_path="account-d.docusign.com",     # demo; "account.docusign.com" for production
    integration_key=integration_key,              # JWT integration key (OAuth client id)
    user_id=user_id,                              # impersonated user's GUID (consent granted)
    private_key=Path("private_key.pem").read_bytes(),
)

pdf = ContractGenerator().generate(
    "contract", data,
    {"party.name", "party.email", "sig.name", "sig.date"},  # expected fields
    {"party.name", "sig.name", "sig.date"},                 # required fields
)

envelope_id = DocuSignSender.for_live_docusign(config).send_for_signature(SendRequest(
    "Consulting Services Agreement",
    pdf,
    "Please sign: Consulting Services Agreement",
    [Signer("Jane Doe", "jane@example.com")],
))
```

`scripts/live_send.py` is a ready-made version of this for manual testing.

### Signature boxes

A form field whose name **contains** `DocusignSignHere` (e.g. `DocusignSignHere1`, built with
`FieldNaming.sign_here(1)`) is converted by DocuSign into a SignHere tab because
`EnvelopeFactory` always sends the document with `transform_pdf_fields="true"`. The trailing
index only keeps names unique; converted tabs go to `assign_tabs_to_recipient_id` (`"1"`, the
first signer). The bundled template's signature box is
`<input name="DocusignSignHere1" id="sig.signature" />`.

### Required fields

`ContractGenerator.generate(template_name, data, expected_field_names, required_field_names)`
marks the given fields' AcroForm **Required** flag. Combined with `transform_pdf_fields="true"`,
DocuSign's auto-converted tabs inherit the required attribute — so `required_field_names` controls
"must be filled before signing" in both the PDF and DocuSign, in one place.

### Testing without DocuSign credentials

`EnvelopeFactory` (builds the `EnvelopeDefinition`) and `DocuSignSender` (with a fake
`DocuSignClient`) are unit-tested with no network calls. `JwtAuthenticator` and
`EsignDocuSignClient` do real network I/O and are exercised only by
`tests/docusign/test_docusign_live.py`, which is skipped unless `DOCUSIGN_LIVE_TEST=true` and the
corresponding `DOCUSIGN_*` environment variables are set (see the module docstring). Run it with:

```bash
DOCUSIGN_LIVE_TEST=true \
DOCUSIGN_ACCOUNT_ID=... DOCUSIGN_INTEGRATION_KEY=... DOCUSIGN_USER_ID=... \
DOCUSIGN_PRIVATE_KEY_PATH=./private_key.pem \
DOCUSIGN_SIGNER_NAME="Jane Doe" DOCUSIGN_SIGNER_EMAIL=jane@example.com \
uv run pytest tests/docusign/test_docusign_live.py -s
```

### Scope & caveats

- Only JWT Grant auth is supported (no authorization-code / implicit flows).
- Tabs are auto-detected from the AcroForm; there's no explicit per-tab placement API.
- With multiple signers, auto-detected tabs are all assigned to the first signer — field names do
  not route tabs to individual signers. Single-signer envelopes are the supported path.
- Out of scope: embedded signing (recipient views), envelope status polling.

## Receiving signed documents (Connect webhook)

Once an envelope is completed, [DocuSign Connect](https://developers.docusign.com/platform/webhooks/connect/)
can POST a notification to your endpoint. When the Connect configuration has **"Include Documents"**
enabled, that notification carries the signed PDF(s) inline. `ConnectWebhookParser` turns the raw
notification body back into the field values — the inverse of the send pipeline.

This library provides only the parsing method; wiring it to an HTTP route is up to you.

```python
from contract_generator.docusign.webhook import ConnectWebhookParser

# raw_body: the exact request body bytes your endpoint received.
envelope = ConnectWebhookParser().parse(raw_body)

if envelope.is_completed:
    values = envelope.fields()        # merged across the envelope's documents
    # values["party.name"] -> "Jane Doe"
    # values["agree.terms"] -> "true"

    for doc in envelope.documents:
        ...  # doc.name, doc.type ("content" / "summary"), doc.pdf_bytes, doc.fields
```

`SignedEnvelope` exposes `envelope_id`, `status`, and the tuple of `SignedDocument`s (each with its
`document_id`, `name`, `type`, decoded `pdf_bytes`, and parsed `fields`). Parsing is
**status-agnostic**: a notification for a not-yet-completed envelope (or one sent without
documents) parses successfully into an empty `documents` tuple rather than raising — inspect
`status` / `is_completed` to decide what to do. The completion-certificate ("summary") document
has no form and parses to empty fields. Malformed JSON, a missing `data` object, or invalid base64
`PDFBytes` raise `WebhookParseError`.

### Verifying the HMAC signature

If you enable HMAC security on the Connect configuration, DocuSign signs each request. Verify it
against the **raw** request body before parsing:

```python
from contract_generator.docusign.webhook import ConnectHmacVerifier

verifier = ConnectHmacVerifier()
signature = request.headers.get("X-DocuSign-Signature-1")   # may be -1, -2, ... per key
if not verifier.verify(raw_body, signature, hmac_secret):
    ...  # reject the request (401)
# verifier.verify_any(raw_body, [sig1, sig2], hmac_secret) checks multiple keys
```

The comparison is constant-time. Always verify the bytes exactly as received — re-serializing the
parsed JSON changes the bytes and breaks verification.

### Scope & caveats (webhook)

- Only the **JSON** eSignature Connect payload format is parsed (legacy XML
  `DocuSignEnvelopeInformation` is not supported).
- Documents are only present when Connect has "Include Documents" enabled; otherwise the parser
  returns an empty documents tuple. Fetching them from the API instead is out of scope.

## Running as a Temporal worker (temporal-worker-k8s rock)

The generator can run as a [Temporal](https://temporal.io/) worker packaged as an OCI
[rock](https://documentation.ubuntu.com/rockcraft/), suitable as the workload (`oci-image`)
resource for the [`temporal-worker-k8s`](https://charmhub.io/temporal-worker-k8s?channel=2.0/stable)
charm. The worker registers the `ContractSigningWorkflow` workflow on the configured task queue;
the workflow takes a **template name + parameters**, generates the fillable PDF, and sends it to
DocuSign, returning the envelope id.

### Workflow contract

Workflow type `ContractSigningWorkflow`; activities `generate_pdf` then `send_to_docusign`
(2-minute start-to-close timeout, up to 3 attempts each). The input is a `ContractSigningRequest`
dataclass, serialized with Temporal's default JSON converter (snake_case keys):

```python
from contract_generator.temporal import ContractSigningRequest, ContractSigningWorkflow, SignerInfo

request = ContractSigningRequest(
    template_name="contract",                     # resources/templates/contract.html
    parameters={
        "title": "Consulting Services Agreement",
        "provider": "Acme Consulting LLC",
        "client": "Globex Corporation",
        "effectiveDate": "2026-09-13",
        "recital": "The Provider agrees to deliver consulting services.",
    },
    expected_field_names=frozenset({"party.name", "party.email"}),  # optional
    required_field_names=frozenset({"party.name"}),  # -> required DocuSign tabs
    document_name="Consulting Agreement",
    email_subject="Please sign: Consulting Agreement",
    signers=(SignerInfo("Jane Doe", "jane@example.com"),),
)

# A Temporal client (anywhere) starts the workflow on the worker's task queue:
envelope_id = await client.execute_workflow(
    ContractSigningWorkflow.generate_and_send, request,
    id="contract-123", task_queue=os.environ["TEMPORAL_QUEUE"],
)
```

Clients in other languages start workflow type `ContractSigningWorkflow` with a JSON object using
the same snake_case keys (`signers` entries: `name`, `email`, `routing_order`).

The bundled templates ship inside the installed package, so `template_name` resolves without
mounting any template files.

### Running locally

```bash
TEMPORAL_QUEUE=contracts uv run contract-generator-worker   # needs a Temporal server on :7233
```

### Environment variables

Injected by the charm (core connection):

| Variable                   | Purpose                                                  | Default          |
|----------------------------|----------------------------------------------------------|------------------|
| `TEMPORAL_HOST`            | Temporal frontend `host:port`                            | `localhost:7233` |
| `TEMPORAL_NAMESPACE`       | Temporal namespace                                       | `default`        |
| `TEMPORAL_QUEUE`           | task queue to poll (**required**)                        | —                |
| `TEMPORAL_TLS_ROOT_CAS`    | root CA PEM for a TLS connection                         | none (plaintext) |
| `TEMPORAL_PROMETHEUS_PORT` | if set, serves worker metrics at `/metrics` on this port | disabled         |

DocuSign credentials (set via the charm's `environment` config), read by the `send_to_docusign`
activity to build a `DocuSignConfig`:

| Variable                                                | Purpose                                      |
|---------------------------------------------------------|----------------------------------------------|
| `DOCUSIGN_ACCOUNT_ID`                                   | account GUID                                 |
| `DOCUSIGN_OAUTH_BASE_PATH`                              | OAuth host, e.g. `account-d.docusign.com`    |
| `DOCUSIGN_INTEGRATION_KEY`                              | integration key (OAuth client id)            |
| `DOCUSIGN_USER_ID`                                      | impersonated user GUID                       |
| `DOCUSIGN_PRIVATE_KEY` *or* `DOCUSIGN_PRIVATE_KEY_PATH` | RSA private key PEM (inline) or a path to it |

### Building and using the rock

```bash
rockcraft pack                 # produces contract-generator-worker_0.1.0_amd64.rock
# upload the rock to your registry / import it, then attach it as the charm resource:
juju deploy temporal-worker-k8s --channel 2.0/stable
juju attach-resource temporal-worker-k8s oci-image=<your-registry>/contract-generator-worker:0.1.0
```

The rock is built on `ubuntu@26.04` with the distro `python3` plus Pango/HarfBuzz. `uv sync
--locked --no-dev` installs the project into `/app/venv`, and `/app/scripts/start-worker.sh`
execs `/app/venv/bin/contract-generator-worker`.

### Scope & caveats (worker)

- Implements the **core** Temporal connection (host/namespace/queue/TLS) plus optional Prometheus
  metrics. Activities are synchronous and run on a thread pool; the worker shuts down gracefully
  on `SIGTERM`/`SIGINT`.
- The generated PDF passes between the two activities through workflow history; this is fine for
  typical contracts but note Temporal's ~2 MB payload limit for very large documents.

## License

This project is licensed under the Apache License, Version 2.0. See the
[LICENSE](LICENSE) file for the full text.

Copyright 2026 Emre Aydin

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this project except in compliance with the License. You may obtain a copy of the
License at <https://www.apache.org/licenses/LICENSE-2.0>.
