# AI Podcast Agent 🤖

An intelligent agent that automates manual portions of your podcast workflow, including copying podcast data from Google Sheets and uploading files to Google Drive.

## Features ✨

- 📊 **Auto-extracts** podcast titles and descriptions from Google Sheets
- 🎵 **Finds latest** podcast files from Google Cloud Storage
- 📁 **Uploads to Google Drive** with proper naming
- 🔗 **Generates shareable links** automatically
- 💬 **Natural language interface** - just tell it what you want
- 🛡️ **Error handling** and logging for reliability

## What It Does

The agent automates this workflow:

1. **Reads your Google Sheets** → Finds the latest podcast output with title/description
2. **Checks Google Cloud Storage** → Locates the most recent podcast audio file
3. **Downloads and uploads** → Transfers the file to your Google Drive folder
4. **Renames the file** → Uses the podcast title as the filename
5. **Provides Drive link** → Gives you a shareable Google Drive URL

## Quick Start 🚀

### 1. Install Dependencies

```bash
pip install -r agent_requirements.txt
```

### 2. Ensure Required Files

Make sure these files are in your project directory:
- `jmio-google-api.json` (Google service account credentials)
- `.env` (with `SHARE_SHEET_WITH_EMAIL` variable)

### 3. Start the Agent

```bash
python start_agent.py
```

### 4. Use Commands

```
You: upload latest podcast
Agent: ✅ Successfully uploaded podcast!

**Title:** AWS AI Agent Marketplace and OpenAI's $30B Oracle Deal
**Output ID:** 219
**Source:** podcasts/aws_ai_agent_marketplace_20250127.mp3
**Drive Link:** https://drive.google.com/file/d/1abc123.../view
```

## Available Commands 💬

| Command | Description |
|---------|-------------|
| `upload latest podcast` | Find and upload the latest podcast to Google Drive |
| `transfer podcast` | Same as above |
| `help` | Show detailed help and current settings |
| `quit` / `exit` | Close the agent |

## Configuration 🔧

The agent uses these settings (configurable in `agent_config.json`):

- **Google Drive Folder:** `13G1L2HSLwdPJHuUoKT0DT8j1IiqHpm8u`
- **GCS Source:** `jmio-podcast-storage/podcasts/`
- **Supported Formats:** MP3, WAV, M4A, AAC
- **Max Filename Length:** 100 characters
- **Temp Directory:** `/tmp` (auto-cleanup enabled)

## How It Works 🔍

### 1. Google Sheets Integration
- Connects to your Google Sheets using service account
- Reads the "Outputs" tab
- Finds the row with the highest "Output ID"
- Extracts title using regex: `Title:\s*([^\n]+)`
- Extracts description using regex: `Description(?:\s+Short)?:\s*([^\n]+)`

### 2. Google Cloud Storage
- Lists all files in the `podcasts/` folder
- Filters for audio file extensions
- Sorts by creation time to find the latest
- Downloads to temporary location

### 3. Google Drive Upload
- Sanitizes the podcast title for filename use
- Uploads to the specified Drive folder: [Your Drive Folder](https://drive.google.com/drive/folders/13G1L2HSLwdPJHuUoKT0DT8j1IiqHpm8u?usp=sharing)
- Sets proper permissions and metadata
- Returns shareable link

### 4. Filename Sanitization
- Removes invalid characters: `<>:"/\|?*`
- Limits length to 100 characters
- Preserves original file extension
- Example: `"AWS AI Agent Marketplace & OpenAI's Deal.mp3"`

## Error Handling 🛡️

The agent includes comprehensive error handling:

- ✅ **Missing credentials** → Clear error messages
- ✅ **No podcast found** → Graceful failure with explanation
- ✅ **Upload failures** → Retry logic and detailed logging
- ✅ **Network issues** → Timeout handling
- ✅ **File cleanup** → Automatic temp file removal

## Logs and Debugging 📝

- **INFO level logging** shows progress and success messages
- **ERROR level logging** captures failures with details
- **Debug output** includes file sizes, paths, and API responses

Example log output:
```
2025-01-27 10:30:15 - INFO - ✅ Google API credentials loaded successfully
2025-01-27 10:30:16 - INFO - 📝 Found latest podcast: ID 219 - AWS AI Agent Marketplace...
2025-01-27 10:30:17 - INFO - 🎵 Found latest podcast file: podcasts/aws_ai_20250127.mp3
2025-01-27 10:30:20 - INFO - ✅ Uploaded to Google Drive: AWS AI Agent Marketplace.mp3
2025-01-27 10:30:20 - INFO - 🔗 Drive link: https://drive.google.com/file/d/1abc.../view
```

## Troubleshooting 🔧

### Common Issues

**❌ "Google credentials file not found"**
- Ensure `jmio-google-api.json` is in the project directory
- Check file permissions

**❌ "SHARE_SHEET_WITH_EMAIL not found"**
- Add the variable to your `.env` file
- Format: `SHARE_SHEET_WITH_EMAIL=your_spreadsheet_id`

**❌ "No podcast title found"**
- Check that your latest output contains "Title:" in the text
- Verify the Outputs sheet has data

**❌ "No podcast file found in GCS"**
- Ensure audio files exist in the `podcasts/` folder
- Check supported formats: MP3, WAV, M4A, AAC

**❌ "Failed to upload file to Google Drive"**
- Verify Google Drive API is enabled
- Check service account has access to the target folder
- Ensure sufficient Google Drive storage space

### Testing Connection

```bash
python -c "from ai_agent import PodcastAgent; agent = PodcastAgent(); print('✅ Agent initialized successfully')"
```

## Security 🔒

- **Service Account Authentication** → No OAuth tokens stored locally
- **Temporary File Cleanup** → Files automatically deleted after upload
- **Read-only Sheets Access** → Agent only reads from Google Sheets
- **Scoped Permissions** → Minimal required API access

## File Structure 📁

```
├── ai_agent.py              # Main agent implementation
├── start_agent.py           # Simple launcher script
├── agent_requirements.txt   # Python dependencies
├── agent_config.json        # Configuration settings
├── AGENT_README.md          # This documentation
├── jmio-google-api.json     # Google service account (required)
└── .env                     # Environment variables (required)
```

## Future Enhancements 🚀

Potential features for future versions:
- 📅 **Scheduled uploads** using cron or Windows Task Scheduler
- 🌐 **Web interface** for remote access
- 📱 **Slack/Discord integration** for notifications
- 🎯 **Batch processing** for multiple files
- 🔄 **Sync verification** to ensure uploads completed successfully
- 📊 **Usage analytics** and reporting

## Support 💡

If you encounter issues:

1. **Check the logs** for detailed error messages
2. **Verify credentials** and permissions
3. **Test individual components** using the troubleshooting commands
4. **Review configuration** in `agent_config.json`

## API Limits 📊

Be aware of these Google API quotas:
- **Sheets API:** 100 requests per 100 seconds per user
- **Drive API:** 1,000 requests per 100 seconds per user
- **Cloud Storage:** Standard bucket operations limits

The agent is designed to stay well within these limits for normal usage.

---

**Ready to automate your podcast workflow?** 🎙️

Run `python start_agent.py` and start with: `upload latest podcast` 