# GitHub Actions Setup for Google Voice Integration

## Overview

This document provides specific instructions for running the Google Voice integration in GitHub Actions environment. The workflow `PPU,PPL15,P1M1,P2&R3&P8&R2M93,P3&R4M1,P4&R5M93,P5&R6M13,R7SL10T7,R6SL7T7,L8GV1SL4T7,L1&L9&L2SL3T7` is now fully supported.

## Prerequisites

### 1. Google Cloud Setup
- ✅ Google Cloud Text-to-Speech API must be enabled
- ✅ Service account with Text-to-Speech permissions
- ✅ Service account JSON key stored as `GOOGLE_CREDS_JSON` secret

### 2. GitHub Secrets Required
All the following secrets must be set in your GitHub repository:

| Secret Name | Description | Required For |
|-------------|-------------|--------------|
| `GOOGLE_CREDS_JSON` | Service account JSON key | Google Voice & Cloud Storage |
| `OPENAI_API_KEY` | OpenAI API key | Text generation steps |
| `ELEVENLABS_API_KEY` | ElevenLabs API key | Alternative voice generation |
| `ANTHROPIC_API_KEY` | Anthropic Claude API key | Text generation with Claude |
| `GEMINI_API_KEY` | Google Gemini API key | Text generation with Gemini |
| `SHARE_SHEET_WITH_EMAIL` | Email for Google Sheets sharing | Workflow management |

## Updated Dependencies

The `requirements.txt` file has been updated to include:

```txt
google-cloud-texttospeech  # ← NEW: Added for Google Voice integration
google-cloud-storage
elevenlabs
openai
pandas
gspread
pydub
anthropic>=0.7.0
google-generativeai>=0.3.0
# ... other existing dependencies
```

## Workflow Analysis

The complete workflow `PPU,PPL15,P1M1,P2&R3&P8&R2M93,P3&R4M1,P4&R5M93,P5&R6M13,R7SL10T7,R6SL7T7,L8GV1SL4T7,L1&L9&L2SL3T7` includes:

### Step-by-Step Breakdown

1. **PPU** - Posted Podcast Update (retrieves existing podcast data)
2. **PPL15** - Posted Podcast Last 15 episodes (gets recent episode data)
3. **P1M1** - Execute Prompt 1 with Model 1
4. **P2&R3&P8&R2M93** - Complex step: Prompt 2 + Response 3 + Prompt 8 + Response 2 with Model 93
5. **P3&R4M1** - Prompt 3 combined with Response 4 using Model 1
6. **P4&R5M93** - Prompt 4 combined with Response 5 using Model 93
7. **P5&R6M13** - Prompt 5 combined with Response 6 using Model 13
8. **R7SL10T7** - Save Response 7 to Location 10 with Title from Response 7
9. **R6SL7T7** - Save Response 6 to Location 7 with Title from Response 7
10. **L8GV1SL4T7** - **Google Voice Step**: 
    - Source: Location 8 (text file)
    - Voice: GV1 (Alnilam from Chirp 3 HD)
    - Destination: Location 4 (audio file)
    - Title: From Response 7
11. **L1&L9&L2SL3T7** - Audio Merge Step:
    - Sources: Locations 1, 9, and 2 (audio files)
    - Destination: Location 3 (merged audio)
    - Title: From Response 7

### Key Google Voice Step: `L8GV1SL4T7`

This step specifically:
1. Downloads the latest text file from Location 8 (Google Cloud Storage)
2. Generates audio using Google Cloud Text-to-Speech with Alnilam voice (Chirp 3 HD)
3. Uploads the generated audio to Location 4 (Google Cloud Storage)
4. Uses Response 7 as the filename/title

## GitHub Actions Environment

### Automatic Setup
The GitHub Actions workflow automatically:

1. **Installs Dependencies**:
   ```yaml
   - name: Install Python dependencies
     run: |
       python -m pip install --upgrade pip
       pip install -r requirements.txt  # Includes google-cloud-texttospeech
   ```

2. **Creates Service Account File**:
   ```yaml
   - name: Create Google credentials file
     run: |
       echo '${{ secrets.GOOGLE_CREDS_JSON }}' > jmio-google-api.json
   ```

3. **Sets Environment Variables**:
   ```yaml
   - name: Set up environment variables
     run: |
       echo "OPENAI_API_KEY=${{ secrets.OPENAI_API_KEY }}" >> $GITHUB_ENV
       echo "ELEVENLABS_API_KEY=${{ secrets.ELEVENLABS_API_KEY }}" >> $GITHUB_ENV
       # ... other environment variables
   ```

4. **Installs System Dependencies**:
   ```yaml
   - name: Install system dependencies
     run: |
       sudo apt-get update
       sudo apt-get install -y ffmpeg  # Required for audio processing
   ```

### Runtime Verification

The workflow includes environment variable checks:

```bash
# Debug: Check if environment variables are set
if [ -n "$OPENAI_API_KEY" ]; then
  echo "✅ OPENAI_API_KEY is set (length: ${#OPENAI_API_KEY})"
else
  echo "❌ OPENAI_API_KEY is not set"
fi
# ... similar checks for other APIs
```

## Testing

### Local Testing
Run the comprehensive test suite:

```bash
python test_full_workflow_github_actions.py
```

This tests:
- ✅ Requirements file completeness
- ✅ Google TTS dependency availability
- ✅ Service account configuration
- ✅ Workflow pattern recognition
- ✅ GitHub Actions environment compatibility
- ✅ FFmpeg availability
- ✅ Workflow execution simulation

### GitHub Actions Testing
The workflow includes built-in testing:

```yaml
- name: Test Environment Variables
  run: |
    python test_env_vars.py
```

## Troubleshooting

### Common Issues

1. **Google TTS API Not Enabled**
   - **Error**: `403 Cloud Text-to-Speech API has not been used in project`
   - **Solution**: Enable the API at https://console.developers.google.com/apis/api/texttospeech.googleapis.com/overview

2. **Service Account Permissions**
   - **Error**: Permission denied errors
   - **Solution**: Ensure service account has `Cloud Text-to-Speech Client` role

3. **Missing Dependencies**
   - **Error**: `ModuleNotFoundError: No module named 'google.cloud.texttospeech'`
   - **Solution**: Verify `google-cloud-texttospeech` is in requirements.txt

4. **Audio Merging Issues**
   - **Error**: FFmpeg errors during audio merging
   - **Solution**: Ensure Google Voice step runs successfully first

### Debug Commands

Add these to your workflow for debugging:

```yaml
- name: Debug Google TTS Setup
  run: |
    python -c "from google.cloud import texttospeech; print('✅ Google TTS imported')"
    python -c "import os; print(f'Service account exists: {os.path.exists(\"jmio-google-api.json\")}')"
```

## Monitoring

### Artifacts
The workflow automatically uploads:

- **Generated Audio Files**: `generated-audio-files-${{ github.run_id }}`
- **Pipeline Logs**: `pipeline-logs-${{ github.run_id }}`

### Success Indicators

Look for these log messages:
- `✅ Google Text-to-Speech client configured`
- `- Step X: L8GV1SL4T7 (Google Voice Step)`
- `✅ Google TTS audio chunk saved`
- `Google Voice audio generated and saved to Google Cloud Storage`

## Production Deployment

### Manual Trigger
The workflow can be triggered manually with:

```yaml
on:
  workflow_dispatch:
    inputs:
      custom_topic:
        description: 'Custom topic for the podcast (optional)'
        required: false
        type: string
      workflow_id:
        description: 'Specific workflow ID to run (optional)'
        required: false
        type: string
        default: ''
```

### Execution
To run the specific workflow:

1. Go to GitHub Actions tab
2. Select "Run AI Podcast Pipeline"
3. Click "Run workflow"
4. Leave inputs blank to use default settings
5. The system will execute: `PPU,PPL15,P1M1,P2&R3&P8&R2M93,P3&R4M1,P4&R5M93,P5&R6M13,R7SL10T7,R6SL7T7,L8GV1SL4T7,L1&L9&L2SL3T7`

## Performance Expectations

### Timing Estimates
- Google Voice generation: ~2-5 seconds per chunk
- Audio merging: ~1-3 seconds per file
- Total workflow: ~5-15 minutes depending on text length

### Resource Usage
- Memory: ~512MB for audio processing
- Storage: Generated audio files (typically 1-50MB each)
- Network: API calls to Google Cloud, OpenAI, ElevenLabs, Anthropic

## Security Notes

- Service account JSON is created temporarily and cleaned up after workflow
- Generated audio files are uploaded as artifacts with 7-day retention
- Logs are retained for 30 days
- All API keys are stored as encrypted GitHub secrets

## Success Confirmation

A successful run will show:
1. All environment variables detected
2. Google Voice step executing without errors
3. Audio files generated and uploaded to Google Cloud Storage
4. Audio merging completing successfully
5. Artifacts uploaded for download

The final output should include the merged podcast episode ready for publication.