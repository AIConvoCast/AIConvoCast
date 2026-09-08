# AIConvoCast Gmail OAuth Setup

This setup sends podcast emails **from `AIConvoCast@gmail.com`** to
**`ianeoconnell@gmail.com`**. It does not use or store Ian's Gmail password or
app password. The only mail credential used by the automation is a revocable
OAuth token with Google's send-only `gmail.send` permission.

## 1. Configure the existing Google Cloud project

The local `client_secret.json` is already a Desktop OAuth client for project
`jmio-434920`, so it can be reused. Keep that file private.

1. Open the [Gmail API page for jmio-434920](https://console.cloud.google.com/apis/library/gmail.googleapis.com?project=jmio-434920) and click **Enable**.
2. Open [Google Auth Platform](https://console.cloud.google.com/auth/overview?project=jmio-434920).
3. Under **Branding**, use `AI Convo Cast` as the app name and complete the required contact fields.
4. Under **Audience**, select **External**. While testing, add `AIConvoCast@gmail.com` as a test user.
5. Under **Data Access**, add only this scope:
   `https://www.googleapis.com/auth/gmail.send`
6. Under **Clients**, confirm there is a **Desktop app** OAuth client. The existing local `client_secret.json` is already in that format. If the client was deleted, create a new Desktop app client and download its JSON over the existing local file.

Google OAuth projects left in **Testing** expire test-user grants after seven
days. Once the test works, change the Audience publishing status to
**In production**. A personal-use app can remain unverified, although Google
will show an unverified-app warning and enforce its user cap.

## 2. Authorize AIConvoCast locally

From this repository, run:

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

## 3. Test without regenerating a podcast

The repository already has the completed local merged MP3. Resend it with the
latest real title/description downloaded from the existing GCS description
folder:

```powershell
python resend_latest_podcast_email.py
```

Alternatively, send the MP3 with a clearly marked OAuth test description:

```powershell
python send_test_podcast_email.py
```

Both recovery commands force the OAuth backend and cannot fall back to SMTP.

## 4. Configure GitHub Actions

1. Open the repository on GitHub.
2. Go to **Settings → Environments → production**.
3. Under **Environment secrets**, create `GMAIL_OAUTH_TOKEN_B64`.
4. Open local `gmail_oauth_token.b64`, copy its entire content, paste it as the
   secret value, and save it. Do not paste it into a workflow file. GitHub
   encrypts environment secrets; base64 itself is not encryption.
5. Run **Actions → Run AI Podcast Pipeline → Run workflow**.
6. Confirm the preflight reports `GMAIL_OAUTH_TOKEN_B64` as set and the final
   email arrives from AIConvoCast.

After the OAuth test succeeds, delete `PODCAST_SMTP_USERNAME` and
`PODCAST_SMTP_PASSWORD` from both locations if they exist:

- **Settings → Environments → production → Environment secrets**
- **Settings → Secrets and variables → Actions → Repository secrets**

Also remove any SMTP variables from the local `.env`. The updated workflows do
not read them.

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
- **`access_denied` or app blocked:** Confirm AIConvoCast is listed as a test
  user and that only `gmail.send` is requested.
- **Advanced Protection:** Google blocks app passwords and can also block
  unverified third-party apps requesting Gmail data. Do not weaken account
  security just for this automation; a verified OAuth app or a domain-backed
  transactional sender is safer in that case.
- **`invalid_grant`:** Delete only `gmail_oauth_token.json`, rerun
  `configure_gmail_oauth.py`, and replace the GitHub token secret.
- **Message too large:** Gmail messages have an approximately 25 MB total
  attachment limit. The current generated episode is about 10 MB.
