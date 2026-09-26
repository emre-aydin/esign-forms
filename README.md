# esign-forms

Render **Jinja2 HTML templates** into **PDFs with fillable AcroForm fields**, send them to
**DocuSign** for signature, and read the filled/signed values back. Use it as a Python library,
or as the `esign-forms` **CLI** from any language (e.g. a Go service calling it as a
subprocess).

Fillable regions are ordinary **HTML form controls** (`<input>`, `<textarea>`, checkbox, radio,
`<select>`) in your template. [WeasyPrint](https://weasyprint.org/) renders them straight into
interactive AcroForm fields, and [pypdf](https://pypdf.readthedocs.io/) validates and normalizes
the form — no anchor text or coordinate math. DocuSign's tab auto-detection
(`transformPdfFields`) turns those fields into signing tabs.

## Install

```bash
pip install esign-forms              # or: uv tool install esign-forms   (CLI only)
pip install 'esign-forms[worker]'    # + the optional Temporal worker
```

Requires **Python 3.12+** and WeasyPrint's system libraries (**Pango**, HarfBuzz) — a wheel
can't ship these:

- Debian/Ubuntu: `apt-get install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0`
- macOS: `brew install pango`. The renderer finds Homebrew's libraries automatically (it
  defaults `DYLD_FALLBACK_LIBRARY_PATH` to `/opt/homebrew/lib` or `/usr/local/lib` when unset).

Every release also publishes a `constraints.txt` (attached to the GitHub Release) that pins all
dependencies to the versions CI tested. Use it for reproducible installs:

```bash
curl -fsSLO https://github.com/emre-aydin/esign-forms/releases/download/v0.1.0/constraints.txt
uv tool install esign-forms==0.1.0 --constraints constraints.txt
```

## CLI

```
esign-forms generate      --template T --input J [--output PDF]   render a fillable PDF
esign-forms send          --template T --input J                   render + send to DocuSign
esign-forms send-pdf      --pdf PDF    --input J                   send an existing PDF
esign-forms read          --pdf PDF                                print field values
esign-forms parse-webhook --input BODY [--signature S]... [--no-verify] [--pdf-dir DIR]
esign-forms --version
```

- Every file argument accepts **`-`** for stdin (inputs) or stdout (`--output`, default `-`).
  At most one input per invocation may come from stdin.
- `--template` is a Jinja2 HTML file. `{% include %}` / `{% extends %}` and relative
  CSS/image URLs resolve from the template's directory. Templates read from stdin can't use
  includes or relative URLs.
- Input and output JSON use **camelCase** keys. Unknown keys are rejected, so typos fail fast.
- DocuSign credentials come from the environment (`send`, `send-pdf`):

  | Variable                                                | Purpose                                      |
  |---------------------------------------------------------|----------------------------------------------|
  | `DOCUSIGN_ACCOUNT_ID`                                   | account GUID                                 |
  | `DOCUSIGN_OAUTH_BASE_PATH`                              | OAuth host, e.g. `account-d.docusign.com`    |
  | `DOCUSIGN_INTEGRATION_KEY`                              | integration key (OAuth client id)            |
  | `DOCUSIGN_USER_ID`                                      | impersonated user GUID                       |
  | `DOCUSIGN_PRIVATE_KEY` *or* `DOCUSIGN_PRIVATE_KEY_PATH` | RSA private key PEM (inline) or a path to it |
  | `DOCUSIGN_CONNECT_HMAC_SECRET`                          | `parse-webhook` HMAC secret(s), comma-separated for key rotation |

### JSON contracts

`generate` input (all keys optional):

```json
{
  "data": {"title": "Consulting Services Agreement", "client": "Globex Corporation"},
  "expectedFields": ["party.name", "sig.date"],
  "requiredFields": ["sig.date"]
}
```

`send` input is the `generate` input plus the envelope keys. `send-pdf` input takes only the
envelope keys:

```json
{
  "documentName": "Consulting Services Agreement",
  "emailSubject": "Please sign: Consulting Services Agreement",
  "signers": [{"name": "Jane Doe", "email": "jane@example.com", "routingOrder": 1}]
}
```

Outputs:

| Command         | stdout                                                                                     |
|-----------------|--------------------------------------------------------------------------------------------|
| `generate`      | PDF bytes (or nothing if `--output FILE`)                                                  |
| `send`, `send-pdf` | `{"envelopeId": "..."}`                                                                 |
| `read`          | `{"fields": {"party.name": "Jane Doe", "agree.terms": "true", ...}}`                        |
| `parse-webhook` | `{"envelopeId", "status", "completed", "documents": [{"documentId", "name", "type", "fields", "pdfPath"?}]}` |

`parse-webhook` verifies the raw body against `DOCUSIGN_CONNECT_HMAC_SECRET`, using each
`--signature` (the `X-DocuSign-Signature-N` header values), unless you pass `--no-verify`.
`--pdf-dir` writes each signed PDF as `<documentId>.pdf` and adds its absolute `pdfPath`.

### Errors and exit codes

Failures print `{"error": {"type": "...", "message": "..."}}` to **stderr**:

| Exit | `type`          | Meaning                                                                               |
|------|-----------------|---------------------------------------------------------------------------------------|
| 0    |                 | success                                                                               |
| 1    | `internal`      | unexpected error                                                                      |
| 2    | `invalid_input` | bad arguments, unreadable file, invalid JSON/template/PDF, missing expected fields    |
| 3    | `docusign`      | authenticating with or calling DocuSign failed                                        |
| 4    | `hmac`          | Connect webhook HMAC verification failed                                              |
| 5    | `render`        | HTML→PDF rendering failed (e.g. Pango not installed)                                  |

### Calling from Go

```go
cmd := exec.CommandContext(ctx, "esign-forms", "send",
    "--template", "/opt/app/templates/contract.html", "--input", "-")
cmd.Stdin = bytes.NewReader(reqJSON) // {"data":{...},"documentName":...,"signers":[...]}
cmd.Env = append(os.Environ(),
    "DOCUSIGN_PRIVATE_KEY_PATH=/etc/app/docusign.pem" /* , DOCUSIGN_* ... */)
var stdout, stderr bytes.Buffer
cmd.Stdout, cmd.Stderr = &stdout, &stderr
if err := cmd.Run(); err != nil {
    // exit code via err.(*exec.ExitError).ExitCode(); details: json in stderr.Bytes()
}
var res struct{ EnvelopeID string `json:"envelopeId"` }
_ = json.Unmarshal(stdout.Bytes(), &res)
```

### Installing into a rock

Add a part to the consuming app's `rockcraft.yaml`. The tool is installed at its final path, so
the venv's interpreter symlink and script shebangs stay valid in the image. `base` and
`build-base` must match, and their `python3` must be 3.12 or newer (`ubuntu@24.04` or later).

```yaml
parts:
  esign-forms:
    plugin: nil
    build-snaps: [astral-uv]
    build-packages: [python3, python3-venv, ca-certificates, curl,
                     libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz-subset0]
    override-build: |
      VERSION=0.1.0
      export UV_TOOL_DIR=/opt/esign-forms UV_TOOL_BIN_DIR=/usr/local/bin \
        UV_PYTHON=/usr/bin/python3 UV_PYTHON_DOWNLOADS=never \
        UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
      curl -fsSLo constraints.txt \
        https://github.com/emre-aydin/esign-forms/releases/download/v$VERSION/constraints.txt
      uv tool install "esign-forms==$VERSION" --constraints constraints.txt
      # Smoke test: fails the build if Pango/HarfBuzz can't be loaded.
      echo '<html><body><form><input name="a"/></form></body></html>' > /tmp/t.html
      echo '{}' | esign-forms generate --template /tmp/t.html --input - > /dev/null
      mkdir -p $CRAFT_PART_INSTALL/opt $CRAFT_PART_INSTALL/usr/local/bin
      cp -a /opt/esign-forms $CRAFT_PART_INSTALL/opt/
      cp -a /usr/local/bin/esign-forms $CRAFT_PART_INSTALL/usr/local/bin/
    stage-packages: [python3, libpango-1.0-0, libpangoft2-1.0-0, libharfbuzz-subset0,
                     ca-certificates]
```

Set `XDG_CACHE_HOME=/tmp` (or another writable dir) in the service environment, so fontconfig
can write its cache on a read-only or non-root filesystem.

## Library usage

```python
from pathlib import Path

from esign_forms import FormData, FormGenerator

data = FormData.builder().put("title", "Consulting Services Agreement").build()
# (a plain dict works too)

pdf = FormGenerator().generate(
    Path("examples/contract.html"),    # a Path = template file; a str = template text
    data,
    {"party.name", "sig.date"},        # optional: fields that must exist
    {"sig.date"},                      # optional: fields to mark Required
)
values = FormGenerator().read_values(Path("filled.pdf"))   # bytes, path, or binary stream
```

Validation failures raise `form.PostProcessError` (e.g.
`Expected form fields are missing: [does.not.exist]`). An invalid field name raises
`ValueError`, and a missing template file raises `FileNotFoundError`.

### Read semantics

- Text, textarea and choice fields return the typed value, or `""` if unfilled.
- Checkboxes are normalized to `"true"` / `"false"`. Checked state is decided from the raw `/V`
  name vs the on-appearance state, not `/Opt` lookups.
- Radio groups return the selected option's `value`, or `""` if none is selected.
- Only **terminal** fields are returned. Dotted-name parents (e.g. `party`) are skipped.
- A PDF without an AcroForm returns `{}`. Unreadable input raises `form.ReadError`.

### Pipeline

```
FormData ─▶ Jinja2 (TemplateEngine) ─▶ HTML
         ─▶ WeasyPrint (HtmlToPdfRenderer, pdf_forms=True) ─▶ PDF + AcroForm
         ─▶ pypdf (AcroFormPostProcessor: hierarchy, validate, NeedAppearances) ─▶ bytes

bytes (filled PDF) ─▶ pypdf (FormReader) ─▶ dict[str, str]
```

## Authoring templates

`examples/contract.html` is a complete sample. Templates are rendered by **Jinja2**, with
autoescaping on; undefined variables render as empty strings.

- **Use the bundled font.** Open Sans (SIL OFL) is registered under the family
  `EsignFormsFont` (`render.FONT_FAMILY`), so output doesn't depend on the host's fonts.
- **Give controls explicit dimensions** (`width`/`height`). The widget rectangle is the
  control's CSS box.
- **The control's `name` becomes the AcroForm field name.** Names must satisfy `FieldNaming`:
  start with a letter, and use only letters, digits, `.`, `_` and `-`. Dotted names
  (`party.name`) become a hierarchical field.
- **Signature boxes:** name a text field so it contains `DocusignSignHere` (e.g.
  `DocusignSignHere1`, see `FieldNaming.sign_here(1)`). DocuSign converts it into a SignHere tab.
  All converted tabs go to the first signer, and field names don't route tabs to individual
  signers.

| HTML control              | AcroForm result                                              |
|---------------------------|--------------------------------------------------------------|
| `<input type="text">`     | text field                                                   |
| `<textarea>`              | multiline text field                                         |
| `<input type="checkbox">` | checkbox                                                     |
| `<input type="radio">`    | radio group (one field per `name`, export values = `value`)  |
| `<select>`                | choice field                                                 |

## DocuSign

Sending uses the official [`docusign-esign`](https://pypi.org/project/docusign-esign/) SDK with
**JWT Grant** auth and tab **auto-detection** (`transformPdfFields=true`). Fields marked
required in the PDF become required DocuSign tabs.

### One-time DocuSign app setup

1. Create an Integration Key (OAuth client id) in the DocuSign Admin console, of type **JWT**.
2. Generate an RSA keypair for it; keep the private key (PEM) — DocuSign only stores the public key.
3. Grant consent once for the impersonated user by visiting (demo environment):
   `https://account-d.docusign.com/oauth/auth?response_type=code&scope=signature%20impersonation&client_id=<integration_key>&redirect_uri=<any_registered_uri>`
4. Note the account id (GUID) and the impersonated user id (GUID) from the DocuSign Admin console.

### Sending from Python

```python
from esign_forms.docusign import DocuSignConfig, DocuSignSender, SendRequest, Signer

config = DocuSignConfig.from_env()   # or DocuSignConfig(account_id=..., private_key=..., ...)
envelope_id = DocuSignSender.for_live_docusign(config).send_for_signature(SendRequest(
    "Consulting Services Agreement", pdf, "Please sign", [Signer("Jane Doe", "jane@example.com")],
))
```

### Receiving signed documents (Connect webhook)

With **"Include Documents"** enabled, DocuSign Connect POSTs the signed PDFs inline. Parse the
raw body with `esign-forms parse-webhook` or from Python:

```python
from esign_forms.docusign.webhook import ConnectWebhookParser

envelope = ConnectWebhookParser().parse(raw_body)
if envelope.is_completed:
    values = envelope.fields()      # merged across documents
```

Parsing works regardless of envelope status: a notification without documents parses into an
empty `documents` tuple. Malformed JSON, a missing `data` object, or invalid base64 raises
`WebhookParseError`. Only the JSON Connect format is supported, and the HTTP endpoint itself is
up to you.

### Verifying the HMAC signature

If you enable HMAC security on the Connect configuration, DocuSign signs each request. Verify it
against the **raw** request body before parsing:

```python
from esign_forms.docusign.webhook import ConnectHmacVerifier

verifier = ConnectHmacVerifier()
signature = request.headers.get("X-DocuSign-Signature-1")   # may be -1, -2, ... per key
if not verifier.verify(raw_body, signature, hmac_secret):
    ...  # reject the request (401)
# verifier.verify_any(raw_body, [sig1, sig2], hmac_secret) checks multiple keys
```

The comparison is constant-time. Always verify the bytes exactly as received — re-serializing the
parsed JSON changes the bytes and breaks verification.

### Scope & caveats

- JWT Grant auth only; no explicit per-tab placement; single-signer envelopes are the supported
  path.
- Out of scope: embedded signing, envelope status polling, legacy XML Connect payloads, and
  fetching documents from the API when the webhook omits them.

## Temporal worker (optional)

`pip install 'esign-forms[worker]'` adds the `esign-forms-worker` command. It registers the
`FormSigningWorkflow` (activities `generate_pdf` then `send_to_docusign`, with a 2-minute timeout
and 3 attempts each). Without the extra installed, the command exits with an install hint.

```python
from esign_forms.temporal import FormSigningRequest, FormSigningWorkflow, SignerInfo

request = FormSigningRequest(
    template_path="/srv/templates/contract.html",   # on the worker's filesystem
    parameters={"title": "Consulting Services Agreement"},
    required_field_names=frozenset({"party.name"}),
    document_name="Consulting Agreement",
    email_subject="Please sign",
    signers=(SignerInfo("Jane Doe", "jane@example.com"),),
)
envelope_id = await client.execute_workflow(
    FormSigningWorkflow.generate_and_send, request, id="form-123", task_queue="forms",
)
```

| Variable                   | Purpose                                                  | Default          |
|----------------------------|----------------------------------------------------------|------------------|
| `TEMPORAL_HOST`            | Temporal frontend `host:port`                            | `localhost:7233` |
| `TEMPORAL_NAMESPACE`       | Temporal namespace                                       | `default`        |
| `TEMPORAL_QUEUE`           | task queue to poll (**required**)                        | —                |
| `TEMPORAL_TLS_ROOT_CAS`    | root CA PEM for a TLS connection                         | none (plaintext) |
| `TEMPORAL_PROMETHEUS_PORT` | if set, serves metrics at `/metrics` on this port        | disabled         |

The `DOCUSIGN_*` variables from the CLI section also apply. The PDF passes between the two
activities through workflow history, so keep Temporal's ~2 MB payload limit in mind.

## Development

```bash
mise install                    # Python 3.13 + uv (from mise.toml)
uv sync                         # .venv with dev tools and the worker extra
uv run pytest                   # tests (live DocuSign test skipped unless DOCUSIGN_LIVE_TEST=true)
uv run ruff check src tests scripts && uv run ruff format --check src tests scripts
uv run mypy
uv build
```

The live DocuSign test (`tests/docusign/test_docusign_live.py`) and `scripts/live_send.py`
exercise real JWT auth and envelope creation. See their docstrings for the environment
variables they need.

### Releasing

1. One-time setup: on pypi.org, add a **pending trusted publisher** for project `esign-forms`:
   owner `emre-aydin`, repo `esign-forms`, workflow `release.yml`, environment `pypi`. Create
   the `pypi` environment under the repo's Settings → Environments.
2. Bump `version` in `pyproject.toml` (`uv version --bump minor`), commit, then tag and push:
   `git tag v0.2.0 && git push origin v0.2.0`.
3. `.github/workflows/release.yml` then runs the tests, checks that the tag matches the version,
   builds, exports `constraints.txt` from `uv.lock`, smoke-tests the wheel, publishes to PyPI,
   and creates a GitHub Release with the wheel, sdist and `constraints.txt`.

## License

This project is licensed under the Apache License, Version 2.0. See the
[LICENSE](LICENSE) file for the full text.

Copyright 2026 Emre Aydin

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this project except in compliance with the License. You may obtain a copy of the
License at <https://www.apache.org/licenses/LICENSE-2.0>.
