# AI Podcast Workflow Pipeline

A comprehensive AI workflow system for generating podcast content using OpenAI and Eleven Labs APIs.

## Features

- **OpenAI Integration**: Generate content using various GPT models with web search capabilities
- **Eleven Labs Integration**: Convert text to speech using configurable voice settings
- **Google Drive Integration**: Download and upload files automatically
- **Workflow Automation**: Chain multiple steps together for complex content generation
- **Google Sheets Management**: Centralized configuration and logging

## New: Eleven Labs Integration

The pipeline now supports Eleven Labs text-to-speech conversion with the following features:

### Workflow Step Pattern: `L8E1SL4`

- **L8**: Location ID 8 (source folder to download latest text file)
- **E1**: Eleven Labs configuration ID 1 (voice settings)
- **SL4**: Save Location ID 4 (destination folder for generated audio)

### Eleven Labs Configuration

The "Eleven" tab contains voice configurations:

| Eleven ID | Voice | Model | Stability | Similarity Boost | Style | Speed |
|-----------|-------|-------|-----------|------------------|-------|-------|
| 1 | Liam | eleven_multilingual_v2 | 0.39 | 0.7 | 0.5 | 1.06 |

### Setup Requirements

1. **Eleven Labs API Key**: Add to your `.env` file:
   ```
   ELEVENLABS_API_KEY=your-elevenlabs-api-key
   ```

2. **Install ElevenLabs Client**: The pipeline uses the official ElevenLabs Python client:
   ```bash
   pip install elevenlabs
   ```

3. **Voice ID Configuration**: The Liam voice ID is already configured:
   ```python
   voice_mapping = {
       "1": "21m00Tcm4TlvDq8ikWAM",  # Liam voice ID from Eleven Labs
   }
   ```

4. **Google Drive Permissions**: Ensure your service account has access to the source and destination folders.

### Example Workflow

Workflow ID 11 demonstrates the Eleven Labs integration:
- **Workflow Code**: `L8E1SL4`
- **Description**: Downloads the latest text file from Location 8 (Scripts folder), converts it to speech using Eleven Labs configuration 1 (Liam voice), and saves the audio to Location 4 (Eleven Labs Generated Audio folder)

### How It Works

1. **Download Text**: Retrieves the most recent text file from the specified Google Drive folder
2. **Generate Audio**: Uses ElevenLabs API with the configured voice settings (stability, similarity_boost, style, speed)
3. **Upload Audio**: Saves the generated MP3 file to the destination folder
4. **Logging**: Records all steps and results in the Workflow Steps tab

### Testing

Run the test script to verify your Eleven Labs setup:
```bash
python test_eleven_labs.py
```

This will test both API connection and voice generation using the Liam voice ID.

## Installation

### Local Setup

1. Install required packages:
   ```bash
   pip install -r requirements.txt
   ```

2. Set up environment variables in `.env`:
   ```
   OPENAI_API_KEY=your-openai-api-key
   ELEVENLABS_API_KEY=your-elevenlabs-api-key
   ```

3. Configure Google Sheets credentials:
   - Place your service account JSON file as `jmio-google-api.json`
   - Update `SHARE_SHEET_WITH_EMAIL` in the script

### GitHub Actions Setup

The repository includes automated GitHub Actions workflows for running the AI podcast pipeline.

#### Prerequisites

1. **Repository Secrets**: Add the following secrets to your GitHub repository:
   - `OPENAI_API_KEY`: Your OpenAI API key
   - `ELEVENLABS_API_KEY`: Your Eleven Labs API key
   - `GOOGLE_CREDS_JSON`: The contents of your Google service account JSON file
   - `SHARE_SHEET_WITH_EMAIL`: Email address to share Google Sheets with

2. **Google Drive Permissions**: Ensure your service account has access to all required Google Drive folders.

#### Workflow Triggers

The pipeline can be triggered in several ways:

1. **Manual Trigger (Recommended)**:
   - Go to Actions tab in your repository
   - Select "Run AI Podcast Pipeline"
   - Click "Run workflow"
   - Optionally provide:
     - Custom topic for the podcast
     - Specific workflow ID to run
     - Force run flag

2. **Automatic on Push**:
   - Triggers when you push changes to `ai_podcast_pipeline_for_cursor.py`, `requirements.txt`, or the workflow file
   - Only runs on the `main` branch

3. **Scheduled (Daily)**:
   - Automatically runs daily at 9 AM UTC
   - Perfect for daily news podcasts

#### Workflow Features

- **Artifact Upload**: Generated audio files and logs are saved as artifacts
- **Error Handling**: Comprehensive error logging and notifications
- **Timeout Protection**: 30-minute timeout to prevent infinite runs
- **Cleanup**: Automatic cleanup of temporary files
- **System Dependencies**: Installs ffmpeg for audio processing

#### Accessing Results

1. **Audio Files**: Download the `generated-audio-files-{run_id}` artifact
2. **Logs**: Download the `pipeline-logs-{run_id}` artifact for debugging
3. **Google Sheets**: Check the "Outputs" and "Workflow Steps" tabs for detailed results

#### Customization

To modify the workflow:
1. Edit `.github/workflows/ai_podcast_pipeline.yml`
2. Adjust the schedule, timeout, or add new steps
3. Commit and push to trigger the updated workflow

## Usage

Run the pipeline:
```bash
python ai_podcast_pipeline_for_cursor.py
```

The script will:
1. Load or create the Google Sheet with all required tabs
2. Process active requests in the "Requests" tab
3. Execute workflow steps according to the "Workflow Code"
4. Log all activities in the "Workflow Steps" tab
5. Save outputs in the "Outputs" tab

## Workflow Code Syntax

### Standard Steps
- `P1`: Use Prompt ID 1
- `R1`: Use Response 1 from previous outputs
- `P1&R1`: Combine Prompt 1 and Response 1
- `M2`: Use Model ID 2 for this step

### Save Steps
- `R1SL4`: Save Response 1 to Location 4

### Eleven Labs Steps
- `L8E1SL4`: Download from Location 8, use Eleven config 1, save to Location 4

### Audio Merging Steps
- `L1&L9&L2SL3`: Download MP3 from Location 1, latest MP3 from Location 9, latest MP3 from Location 2, merge them, and save to Location 3

**Audio Merging Pattern**: `L{source1}&L{source2}&...&L{sourceN}SL{destination}`
- Combines multiple audio files from different locations
- Supports both specific files (Type: "File") and latest MP3 from folders (Type: "mp3")
- Merges audio files in the order specified
- Saves the combined audio to the destination location

## File Structure

- `ai_podcast_pipeline_for_cursor.py`: Main pipeline script
- `test_eleven_labs.py`: Eleven Labs integration test script
- `requirements.txt`: Python dependencies
- `.env`: Environment variables (create this file)
- `jmio-google-api.json`: Google service account credentials

## Google Sheets Structure

The pipeline manages these tabs:
- **Workflows**: Define workflow steps and configurations
- **Outputs**: Store generated content
- **Requests**: Active workflow requests
- **Prompts**: Reusable prompt templates
- **Models**: Available AI models and settings
- **Workflow Steps**: Detailed execution logs
- **Locations**: Google Drive folder mappings
- **Eleven**: Eleven Labs voice configurations

### Location Types

The **Locations** tab supports different types of file/folder references:

| Type | Description | Usage |
|------|-------------|-------|
| `File` | Specific file URL | Downloads the exact file from Google Drive |
| `Folder` | Folder URL | Used for uploading files to the folder |
| `Text` | Folder URL | Downloads the latest text file from the folder |
| `mp3` | Folder URL | Downloads the latest MP3 file from the folder |

**Example Locations:**
- Location 1: Intro MP3 File (Type: File) - Specific intro audio
- Location 8: Latest Text File in Scripts Folder (Type: Text) - Latest script for Eleven Labs
- Location 9: Latest mp3 in Eleven lab Folder (Type: mp3) - Latest generated audio for merging

## Troubleshooting

### Common Issues

1. **Eleven Labs API Errors**: Check your API key and ensure the elevenlabs package is installed
2. **Google Drive Access**: Verify service account permissions
3. **Missing Dependencies**: Install required packages from requirements.txt

### Voice ID Configuration

The Liam voice ID (`21m00Tcm4TlvDq8ikWAM`) is already configured. To add more voices:
1. Go to Eleven Labs dashboard
2. Navigate to Voice Library
3. Copy the voice ID from the URL or API response
4. Add to the `voice_mapping` in the `get_voice_id_by_eleven_id` function

## License

This project is licensed under the MIT License - see the LICENSE file for details.

### Posted Podcasts Update (PPU)
When the workflow step is `PPU`, the script will update the "Posted Podcasts" tab in the Google Sheet by fetching the latest episodes from the AI Convo Cast Podcast RSS feed. The tab will be fully refreshed with all episodes, including:
- **Posted Podcasts ID**: Sequential integer (oldest episode = 1, newest = highest ID)
- **Title**: The episode title (special characters decoded)
- **Description**: The full episode description (special characters decoded)
- **Description Short**: The description up to "Help support..."

This ensures that the tab is always up to date and that IDs are consistent for referencing.

### Posted Podcast Last (PPL#)
When the workflow step is `PPL#` (e.g., `PPL3`), the script will retrieve the Title and Description Short from the last # posted podcast episodes (by highest Posted Podcasts ID, i.e., the newest episodes) and output them to the Outputs tab. This output can be referenced in future steps using `R#`.
Special characters in titles and descriptions are decoded for readability.