# SCG Prompt Forge

A ComfyUI custom node for **bulk creative prompt generation**. Give it a seed
idea ("guerrilla marketing street shots, think DKNY or American Eagle style
advertising") and it pumps out batches of distinct, shaped prompts — built for
LoRA testing workflows that need hundreds of quality prompts carrying specific
trigger keywords (e.g. hex color codes).

It opens a full-screen forge over the ComfyUI canvas where you can:

- Describe the **seed idea** you're chasing, plus optional things to avoid.
- Optionally add a **reference image** (click, drag in, or Ctrl+V from the
  clipboard). With no seed text, the image's scene becomes the springboard;
  with seed text, the seed stays in charge and can steer how the image is used
  (only its palette, only its subject, and so on).
- List **required keywords** (LoRA triggers, hex codes), either injected into
  every prompt or **rotated** one-per-prompt across the batch.
- Load **wildcard .txt files** (click or drag in — same format as
  scg-wildcards: one option per line, `#` comments ignored). Each file gets an
  editable keyword; every prompt draws its own random line. Reference a file
  as `_name_` in the seed idea or required keywords to control where the value
  lands (keyword-line tokens resolve to the drawn value, so the verbatim check
  still applies); unreferenced files are still woven into every prompt.
- Pick an **output shape** from a dropdown — paragraph description,
  multi-paragraph photography-focused, booru/CSV tag list, Ideogram bbox JSON,
  simple JSON fields, YAML, markdown — or **Custom**, where you describe the
  shape in plain text and the agent runs with it.
- Generate batches of up to 500 prompts. The agent first expands the seed into
  a creative brief plus distinct concept angles, then writes prompts in chunks
  so every prompt gets its own angle instead of 200 near-duplicates.
- Review the batch: edit any prompt in place, delete, **reroll** individual
  prompts, or **Generate more** to append. Prompts missing a required keyword
  are flagged.
- **Save to node** and step through the batch in your workflow, **Copy all**
  to the clipboard, or download the batch as a file:
  - **.txt** — UTF-8, prompts separated by `=== PROMPT n/N ===` lines, so the
    file stays splittable (`/^=== PROMPT \d+\/\d+ ===$/m`) no matter what shape
    the prompts are.
  - **.jsonl** — UTF-8, one JSON-encoded prompt string per line, bulletproof
    for scripts.

## Node outputs

| Output | Type | Notes |
| --- | --- | --- |
| `prompt` | STRING | `prompts[index % count]` — the current prompt. |
| `index` | INT | The effective (wrapped) index that was emitted. |
| `count` | INT | Total prompts in the saved batch. |

The `index` widget defaults its control to **increment**: queue N runs and the
node walks the batch one prompt per run, wrapping around at the end. Set the
control to **fixed** to pin a single prompt.

The node also has a **Copy Batch** button that copies all saved prompts to the
clipboard (blank-line separated).

## Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/SanDiegoDude/scg-prompt-forge.git scg_prompt_forge
```

Then **restart ComfyUI** (the plugin registers two small server routes at
startup). The node appears as **SCG Prompt Forge** under `SCG/PromptForge`.

### Dependencies

For the common case (OpenAI-compatible endpoints like LM Studio, OpenAI, Grok,
Gemini's OpenAI-compat URL), there is **nothing to install** — the agent calls
are proxied through the ComfyUI server using its bundled `aiohttp`.

The only optional dependency is **`google-auth`**, which is required *only* if
you configure a **Vertex AI** provider (see below):

```bash
pip install -r requirements.txt
```

## Configuring AI providers (`.env`)

The agents talk to any **OpenAI-compatible** chat-completions endpoint (LM
Studio, OpenAI, x.ai/Grok, Gemini's OpenAI-compat endpoint, etc.). Providers are
declared in a local `.env` file so that **API keys stay on the server and are
never sent to the browser** — the UI only ever sees each provider's
id/label/model and asks the ComfyUI server to make the call on its behalf.

1. Copy the example file:

   ```bash
   cp .env.example .env
   ```

2. Add one provider per line:

   ```
   AI_PROVIDER_<ID> = Label | model | base_url (blank = official OpenAI) | api_key
   ```

   Examples:

   ```
   AI_PROVIDER_OPENAI = OpenAI (gpt-5.4-mini) | gpt-5.4-mini |  | sk-...
   AI_PROVIDER_GROK   = grok-4.3 | grok-4.3 | https://api.x.ai/v1 | xai-...
   AI_PROVIDER_GEMINI = Gemini 3.5 Flash | gemini-3.5-flash | https://generativelanguage.googleapis.com/v1beta/openai | ...
   AI_PROVIDER_LOCAL  = Local (qwen3) | qwen3-... | http://192.168.0.180:1234 | 123
   ```

   - Leave the `base_url` blank to use the official OpenAI endpoint.
   - A bare host (e.g. `http://192.168.0.180:1234`, LM Studio) automatically gets
     `/v1` appended.
   - Comment a line out with `#` to hide that provider.

3. In the forge UI (**Agent Configuration → Agent settings**), pick your
   provider from the dropdown. After editing `.env`, click **Refresh** to reload
   providers live — no restart needed.

> **Zero-setup fallback:** if this folder has no `.env` of its own, the plugin
> automatically reads the one in a sibling
> [`scg_json_prompt_agent`](https://github.com/SanDiegoDude/scg_json_prompt_agent)
> install, so if you already use that bbox builder there is nothing to configure.

> **Security:** `.env` is git-ignored. Never commit your keys. The proxy only
> exposes provider id/label/model to the browser; URLs and keys remain
> server-side.

### Gemini via Vertex AI

Vertex providers reach Gemini through Vertex's OpenAI-compatible endpoint. They
use a `vertex://PROJECT/LOCATION` base URL and authenticate with Google OAuth
(no static key in the 4th field):

```
AI_PROVIDER_<ID> = Label | model | vertex://PROJECT/LOCATION | [path/to/service-account.json]
```

Replace `PROJECT` with your Google Cloud project id, and `LOCATION` with `global`
(the global endpoint) or a region such as `us-central1`. Leave the 4th field
blank to use Application Default Credentials, or set it to a service-account JSON
path. The server adds the required `google/` model prefix and fetches/refreshes
the OAuth token for you, so nothing sensitive reaches the browser.

**Setup, step by step:**

1. **Enable the API.** In your Google Cloud project, enable the *Vertex AI API*
   and make sure billing is enabled.

2. **Install the auth dependency** into the same environment ComfyUI runs in:

   ```bash
   pip install -r requirements.txt
   ```

3. **Authenticate** — pick one:

   - **Application Default Credentials (simplest).** Install the
     [gcloud CLI](https://cloud.google.com/sdk/docs/install), then run:

     ```bash
     gcloud auth application-default login
     ```

     Leave the 4th `.env` field blank.

   - **Service account.** Create a service account with the *Vertex AI User*
     role, download its JSON key, and put the file path in the 4th `.env` field:

     ```
     AI_PROVIDER_GEMINI = Gemini Vertex | gemini-2.0-flash | vertex://my-project-id/global | /home/me/keys/vertex-sa.json
     ```

4. **Add the provider line** to `.env` (replace the placeholders with your own
   project, region, and model):

   ```
   AI_PROVIDER_GEMINI = Gemini Vertex | gemini-2.0-flash | vertex://my-project-id/us-central1 |
   ```

5. **Restart ComfyUI** once so the provider registers, then select it from the
   picker in **Agent Configuration → Agent settings**. (Later `.env` edits only
   need the **Refresh** button.)

> **Tip:** Gemini "flash/thinking" models spend tokens on internal reasoning, so
> keep **Max tokens** generous (8k+) or replies can come back truncated/empty.

### A note on OpenAI GPT-5 / o-series models

These reasoning models have a slightly different API surface. The server handles
it for you: it sends `reasoning_effort: "low"`, uses `max_completion_tokens`
instead of `max_tokens`, and omits `temperature` (which those models reject).
Other providers use the standard `max_tokens` + `temperature`.

## How it works

- `nodes.py` — the `SCG Prompt Forge` node; steps through the saved batch.
- `providers.py` — parses `.env` and registers the two routes:
  - `GET /scg_prompt_forge/providers` — provider list (no secrets).
  - `POST /scg_prompt_forge/chat` — server-side proxy to the selected provider.
- `web/prompt_forge.js` — the parent extension: hides the batch widget, adds
  the Open Forge / Copy Batch buttons, and bridges the iframe to the node.
- `web/Prompt_Forge.html` — the forge UI (iframe over the ComfyUI canvas):
  batch setup, the two-stage chunked generation pipeline, the reviewable
  prompt list, and the Agent Configuration panel with editable rulesets.

The generation pipeline runs entirely in the overlay (through the chat proxy);
nothing is queued on the ComfyUI graph until you run your own workflow with
the saved batch.

## License

MIT — see [LICENSE](LICENSE).
