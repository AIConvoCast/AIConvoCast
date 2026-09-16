# Podcast reliability and research costs

## Local Gmail and GitHub Gmail are separate

GitHub continues to use its existing `GMAIL_OAUTH_TOKEN_B64` secret. Local runs
default to `gmail_oauth_token.json` beside `podcast_email.py`, independent of the
terminal's current directory. Explicit token environment variables take priority.
No code copies a local grant into GitHub or replaces its working authorization.

A local terminal run with an expired/revoked default grant opens the existing
send-only Google authorization flow after available email backends fail. Sign in
as **AIConvoCast@gmail.com** within three minutes; the saved episode is then sent.
This never opens a browser in GitHub Actions or a non-interactive process.
Set `PODCAST_LOCAL_REAUTHORIZE=false` to disable interactive renewal.

To renew before a run, or when using a non-interactive launcher:

```powershell
python configure_gmail_oauth.py
```

An `invalid_grant` error requires a new grant; repeating a connection attempt
cannot repair a revoked refresh token. Temporary authorization/connection errors
get up to three attempts with backoff. The optional SMTP credentials are a fallback
after a definitive Gmail failure. SMTP also requires valid credentials; a rejected
app password cannot be repaired by retrying. Existing GitHub secrets need no change
when GitHub delivery already works.

If **GitHub** reports `invalid_grant`, renew locally and replace
`GMAIL_OAUTH_TOKEN_B64` under **Settings > Environments > production > Environment
secrets** using the contents of `gmail_oauth_token.b64`. A repository-level secret
does not override an existing environment secret. Never paste token contents into
logs, issues, or commits. Run **Check podcast email authorization** from Actions
to verify the production secret without generating an episode or sending mail.

Both pipeline workflows check email authorization before paid generation. The
check forces a refresh even if the cached access token is still valid, accepts a
working configured SMTP fallback, and stops the run if neither can authenticate.
It does not guarantee later message acceptance or replace saved-email recovery.
The local equivalent is `python podcast_email.py --check-auth`.

Google OAuth apps in **Testing** issue Gmail refresh tokens that expire after
seven days. For unattended use, change the app's publishing status to
**In production** in Google Auth Platform > Audience, then authorize again and
replace the production secret. This removes the testing expiration limit; grants
can still be revoked. See [Google's token expiration documentation](https://developers.google.com/identity/protocols/oauth2#expiration).

## Preserving and recovering an episode

Each generated upload is copied into `generated_mp3/runs/<run>/` before cloud work.
Current-run scripts/audio remain available to subsequent steps even if GCS upload
or authentication fails. Google Sheets audit logging becomes best-effort after
failure, with local JSON records. Named intro/outro downloads are cached in
`generated_mp3/asset_cache/` for later outages. Latest narration is never taken from
an earlier run. Initial workflow configuration still requires Google Sheets; Google
TTS still requires its own valid credentials. An uncached required intro/outro must
be downloaded successfully at least once.

Before email submission, the complete MP3 + description message is saved under
`generated_mp3/email_outbox/`. Its adjacent JSON file records `sending`, `sent`,
`failed`, or `uncertain`. A known rate-limit rejection can retry. A timeout after
submission does **not** automatically resend through another backend, because the
first server may already have accepted the message.

After repairing local email authorization, resend without paying to generate audio
again (replace the filename with the saved message):

```powershell
python podcast_email.py --resend generated_mp3/email_outbox/<message>.eml
```

For `uncertain`/`sending` results, first check Sent and the recipient mailbox; only
if absent, add `--confirm-not-delivered`. Already-sent messages are refused.
Both GitHub pipeline workflows retain generated files as run artifacts for seven
days, including failed runs. Local run archives are retained until you remove them.

ElevenLabs retries temporary connection/rate-limit failures for the affected chunk,
including disconnects during streaming. Real credit exhaustion immediately uses
the existing Google voice fallback. Retries do not replenish ElevenLabs credits.

## Astra research within a comparable budget

Selecting Astra web research runs one bounded **GPT-5.6 Sol source-discovery pass**,
then one **GPT-6 Astra editorial pass**. Sol uses at most six web tool calls, low
search context, low reasoning, and 3,200 output tokens. The improved instructions
require event dates, primary evidence, useful technical implications, independent
corroboration for disputed claims, source attribution, and meaningful new material
for follow-ups. Five weak stories are never preferred to fewer well-supported ones.

Astra receives only the sourced brief. Its complete input is counted through the
Responses input-token endpoint before generation. The application reserves the
highest input rate (including cache writes) plus the maximum possible output cost;
output includes hidden reasoning tokens. Combined reserved cost stays below 3× the
**Sol search pass for the same request**, with an additional 10% margin on Astra's
allowance. Astra uses the default service tier and gets no tools, continuations or
automatic paid retries. If it cannot fit, its token count is unavailable, or its
output adds new source URLs, the workflow keeps the Sol brief. Research timeouts do
not start another possibly billable request.

The historical cost of older Sol runs was not logged. Native hosted search has
variable retrieval-token charges, so no historical dollar guarantee can be inferred
from model token prices alone. Optional `RESEARCH_SOL_BASELINE_USD` in `.env` (or a
GitHub repository variable) further restricts **additional Astra spend** against a
known historical value. Sol discovery itself can vary and is not a hard dollar-capped
request. Do not describe this as a guarantee against every historical run's cost.

Each research run saves both briefs and `research-cost.json`, with token usage,
search calls, input/cache-write cost bounds, reservations, and fallback status.
Verified standard-tier prices on 2026-09-16:
[Astra](https://developers.openai.com/api/docs/models/gpt-6-astra),
[Sol](https://developers.openai.com/api/docs/models/gpt-5.6-sol),
[hosted search](https://developers.openai.com/api/docs/pricing).
The automatic Astra pass stops after 2026-11-21 until the rate card is reverified;
Sol's published promotional prices are only promised through at least that date.

The 2026-09-16 live check used three search calls. Sol cost $0.192303; Astra added
$0.075355; total $0.267658, or 1.392× the matched Sol pass. This was a research-only
check, with no episode publication or email delivery.

## Verification

```powershell
python -m unittest test_google_audio_quality test_google_pronunciations test_podcast_email test_pipeline_recovery test_news_research test_scheduled_podcast test_site -v
```

These are offline tests. Other historical `test_*.py` scripts may call paid services
or initialize the full workflow; do not run blanket test discovery.
