# AIConvoCast Gmail OAuth Setup

This setup sends podcast emails **from `AIConvoCast@gmail.com`** to
**`ianeoconnell@gmail.com`**. It does not use or store Ian's Gmail password or
app password. Gmail API delivery uses a revocable OAuth token with Google's
send-only `gmail.send` permission. SMTP is an optional, separately configured fallback.

## Current configuration and recommended default

On **2026-09-16**, the existing **AIWorkflow** OAuth app in `jmio-434920` was
published as **In production**. A new send-only grant was then created for
`AIConvoCast@gmail.com`, saved locally, and installed as the GitHub `production`
environment's `GMAIL_OAUTH_TOKEN_B64` secret. Local and GitHub authorization
checks passed. Do not move the app back to Testing or renew it every week.

**Publish before authorizing unattended runs.** Testing-mode Gmail grants expire
after seven days; production grants are not subject to that testing limit. The
code automatically refreshes short-lived access tokens using the saved refresh
token. Other invalidation reasons still apply, including revocation, prolonged
non-use, account/security changes, token limits, and applicable access policies.
See [Google's refresh-token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).

## 1. Configure the existing Google Cloud project

The local `client_secret.json` is already a Desktop OAuth client for project
`jmio-434920`, so it can be reused. Keep that file private.

1. Open the [Gmail API page for jmio-434920](https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=jmio-434920) and click **Enable**.
2. Open [Google Auth Platform](https://console.cloud.google.com/auth/overview?project=jmio-434920).
3. Under **Branding**, keep the existing `AIWorkflow` app name and contact fields. The homepage is `https://aiconvocast.com/` and privacy policy is `https://aiconvocast.com/privacy.html`. Completing these fields enabled the previously disabled Publish button.
4. Under [**Audience**](https://console.cloud.google.com/auth/audience?project=jmio-434920), keep **External** and confirm **In production**. If setting up again from Testing, choose **Publish app**, then confirm the change before creating the Gmail grant.
5. Under **Data Access**, add only this scope:
   `https://www.googleapis.com/auth/gmail.send`
6. Under **Clients**, confirm there is a **Desktop app** OAuth client. The existing local `client_secret.json` is already in that format. If the client was deleted, create a new Desktop app client and download its JSON over the existing local file.

Publishing and Google verification are separate. This personal-use app is
published but unverified, so Google can still show an unverified-app warning and
apply its user cap. That does not mean the app is still in Testing.

## 2. Authorize AIConvoCast locally

After confirming **In production**, run from this repository only when initially
setting up or replacing an invalid grant:

```powershell
python configure_gmail_oauth.py
```

A Google page opens. Carefully select `AIConvoCast@gmail.com`, review the single
send-mail permission, and approve it. If Google shows an unverified-app warning,
use **Advanced**, then continue only after confirming the project and requested
scope are yours.

This creates `gmail_oauth_token.json` for local use and
`gmail_oauth_token.b64` for GitHub. Both files are ignored by the repository and
must never be committed. Base64 is only transport encoding, not encryption.

Add these non-secret settings to the local `.env`:

```env
PODCAST_EMAIL_BACKEND=gmail_api
PODCAST_EMAIL_FROM=AIConvoCast@gmail.com
PODCAST_EMAIL_TO=ianeoconnell@gmail.com
GMAIL_OAUTH_TOKEN_FILE=gmail_oauth_token.json
```

## 3. Check authorization without generating or sending anything

Validate the saved grant, including an actual token refresh:

```powershell
python podcast_email.py --check-auth
```

This sends no email and makes no paid generation requests. Both GitHub pipeline
variants run the same check before generating an episode. If Gmail cannot
authenticate, a configured SMTP fallback must authenticate for the check to pass.

## 4. Configure GitHub Actions

1. Open the repository on GitHub.
2. Go to **Settings → Environments → production**.
3. Under **Environment secrets**, create or update `GMAIL_OAUTH_TOKEN_B64`. An existing environment secret takes precedence over a repository secret of the same name.
4. Open local `gmail_oauth_token.b64`, copy its entire content, paste it as the
   secret value, and save it. Do not paste it into a workflow file. GitHub
   encrypts environment secrets; base64 itself is not encryption.
5. Run **Actions → Check podcast email authorization → Run workflow**.
6. Confirm the log says `Email authorization verified via gmail_api. No email sent.` This verifies the actual production secret without regenerating an episode.

Local renewal does not automatically update GitHub. After creating a replacement
grant for GitHub, complete the secret update and check above. Healthy local and
GitHub grants do not require routine replacement.

The workflows also support optional `PODCAST_SMTP_USERNAME` and
`PODCAST_SMTP_PASSWORD` secrets. Keep them only if intentionally using SMTP as a
fallback and its credentials are valid. See [pipeline operations](PIPELINE_OPERATIONS.md).

## 5. Recover an already-generated episode

If email failed, download the failed run's `generated-audio-files-<run-id>` artifact.
Keep the saved `.eml` and its adjacent status `.json` together. After repairing
authorization, explicitly resend that exact message:

```powershell
python podcast_email.py --resend generated_mp3/email_outbox/<message>.eml
```

This command **sends an email** with the saved MP3 and description; it does not
regenerate audio. Already-sent messages are refused. For an uncertain delivery,
check Sent and the recipient mailbox before using `--confirm-not-delivered`.

## Troubleshooting

- **`Ineligible accounts not added`:** First open a private/incognito browser and
  confirm that `AIConvoCast@gmail.com` can sign in directly at
  `https://accounts.google.com` and open its own Gmail inbox. An alias or
  forwarding-only address is not a Google Account and cannot grant OAuth access.
  If it is a standalone account, open **Google Auth Platform → Audience**:
  - If the user type is **Internal**, change it to **External**. Internal apps
    only accept accounts in the Cloud project's Workspace organization.
  - If the publishing status is **Testing**, add AIConvoCast under **Test users**.
  - If the status is already **In production**, do not add a test user; production
    External apps accept Google Accounts directly. Run
    `python configure_gmail_oauth.py` and continue through the personal-use
    unverified-app warning.
  If the existing project cannot be changed to External, create a separate Cloud
  project while signed in as AIConvoCast, enable Gmail API, configure an External
  audience, create a Desktop OAuth client, and replace local
  `client_secret.json` with that downloaded client file.
- **`access_denied` or app blocked:** Confirm the correct account and client,
  that only `gmail.send` is requested, and that the app is In production. Test-user
  allowlists apply only in Testing; do not revert a working production app.
- **Advanced Protection:** Google blocks app passwords and can also block
  unverified third-party apps requesting Gmail data. Do not weaken account
  security just for this automation; a verified OAuth app or a domain-backed
  transactional sender is safer in that case.
- **Gmail `invalid_grant`:** Check the publishing status first. If the grant is
  actually invalid, rerun `configure_gmail_oauth.py` and update the production
  environment secret if GitHub also needs repair. There is no need to delete a
  token file before renewal. Retrying an expired or revoked grant cannot repair it.
- **`gcloud` reports `invalid_grant`:** This is the Google Cloud CLI's separate
  login, not the podcast's Gmail grant. `gcloud auth login` repairs CLI access if
  you need CLI commands; it does not replace `gmail_oauth_token.json` or GitHub's
  Gmail secret. The Gmail helper does not require `gcloud`. Use the Audience
  console page above to inspect OAuth publication, and `--check-auth` to inspect
  podcast email authorization. See [Google's CLI authentication documentation](https://docs.cloud.google.com/sdk/docs/authenticate).
