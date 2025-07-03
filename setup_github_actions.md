# GitHub Actions Setup Guide

This guide will help you set up GitHub Actions to run your AI podcast pipeline automatically.

## Step 1: Add Repository Secrets

1. Go to your GitHub repository
2. Click on **Settings** tab
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret** for each of the following:

### Required Secrets

#### 1. OPENAI_API_KEY
- **Name**: `OPENAI_API_KEY`
- **Value**: Your OpenAI API key (starts with `sk-`)
- **Source**: [OpenAI Platform](https://platform.openai.com/api-keys)

#### 2. ELEVENLABS_API_KEY
- **Name**: `ELEVENLABS_API_KEY`
- **Value**: Your Eleven Labs API key
- **Source**: [Eleven Labs Dashboard](https://elevenlabs.io/app/api-key)

#### 3. GOOGLE_CREDS_JSON
- **Name**: `GOOGLE_CREDS_JSON`
- **Value**: The entire contents of your Google service account JSON file
- **Instructions**:
  1. Open your `jmio-google-api.json` file
  2. Copy the entire JSON content (including all brackets and quotes)
  3. Paste it as the secret value

#### 4. SHARE_SHEET_WITH_EMAIL
- **Name**: `SHARE_SHEET_WITH_EMAIL`
- **Value**: Your email address (e.g., `your-email@gmail.com`)
- **Purpose**: The email address that will have access to the generated Google Sheets

## Step 2: Verify Google Drive Permissions

Ensure your Google service account has access to all required folders:

1. **Scripts Folder**: For downloading latest text files
2. **Eleven Labs Folder**: For uploading generated audio
3. **Podcasts Folder**: For uploading final merged audio
4. **Intro/Outro Files**: For downloading intro and outro audio

## Step 3: Test the Workflow

1. Go to the **Actions** tab in your repository
2. Click on **Run AI Podcast Pipeline**
3. Click **Run workflow**
4. Optionally fill in:
   - **Custom topic**: A specific topic for your podcast
   - **Workflow ID**: Specific workflow to run (default: 12)
   - **Force run**: Check to run even if no changes detected

## Step 4: Monitor Execution

1. Click on the running workflow to see real-time logs
2. Wait for completion (usually 5-15 minutes)
3. Download artifacts:
   - **generated-audio-files-{run_id}**: Contains all generated MP3 files
   - **pipeline-logs-{run_id}**: Contains execution logs

## Troubleshooting

### Common Issues

#### 1. "Permission denied" errors
- **Solution**: Check that your Google service account has access to all required folders
- **Verify**: Try accessing the folders manually with the service account

#### 2. "API key invalid" errors
- **Solution**: Verify your API keys are correct and have sufficient credits
- **Check**: Test your keys locally first

#### 3. "Workflow timeout" errors
- **Solution**: The workflow has a 30-minute timeout. For longer content, consider:
  - Breaking content into smaller chunks
  - Using faster models
  - Optimizing prompts

#### 4. "Missing dependencies" errors
- **Solution**: The workflow automatically installs all dependencies
- **Check**: Ensure your `requirements.txt` is up to date

### Debugging

1. **Check logs**: Download the pipeline-logs artifact
2. **Verify secrets**: Ensure all secrets are properly set
3. **Test locally**: Run the script locally to identify issues
4. **Check Google Sheets**: Verify the "Workflow Steps" tab for detailed logs

## Customization

### Modify Schedule
Edit `.github/workflows/ai_podcast_pipeline.yml`:
```yaml
schedule:
  # Run every Monday at 9 AM UTC
  - cron: '0 9 * * 1'
```

### Add Notifications
Add Slack or email notifications by modifying the workflow file.

### Change Timeout
Modify the timeout value:
```yaml
timeout-minutes: 60  # Increase to 60 minutes
```

## Security Notes

- **Never commit API keys**: Always use GitHub secrets
- **Rotate keys regularly**: Update your API keys periodically
- **Monitor usage**: Check your API usage to avoid unexpected charges
- **Review permissions**: Ensure service accounts have minimal required permissions

## Support

If you encounter issues:
1. Check the workflow logs in the Actions tab
2. Verify all secrets are correctly set
3. Test the script locally first
4. Check the Google Sheets "Workflow Steps" tab for detailed error messages 