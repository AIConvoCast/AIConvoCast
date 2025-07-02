import os
import pandas as pd
import gspread
import requests
import openai
from openai import OpenAI
from pydub import AudioSegment
from dotenv import load_dotenv
import time
import re
import io
import tempfile
import traceback
import json
import sys

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'jmio-google-api.json'
GOOGLE_SHEET_NAME = 'AI Workflow'
GOOGLE_DRIVE_FOLDER_ID = '17XAnga8MC1o23rFhiQ7fcrrqDNhz_-oB'  # Folder to create the sheet in
SHARE_SHEET_WITH_EMAIL = 'ianeoconnell@gmail.com' # <--- CHANGE THIS TO YOUR EMAIL

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-key')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', 'your-elevenlabs-key')

# Instantiate the OpenAI client once using the API key from environment variables
client = OpenAI(api_key=OPENAI_API_KEY)

print(f"[DEBUG] Python version: {sys.version}")
print(f"[DEBUG] requests version: {requests.__version__}")
try:
    import elevenlabs
    print(f"[DEBUG] elevenlabs version: {elevenlabs.__version__}")
except ImportError:
    pass

# -----------------------------------------
# GOOGLE SHEET SUPPORT
# -----------------------------------------
def create_and_setup_google_sheet(gc, sheet_name, folder_id, user_email):
    """Creates and populates a new Google Sheet with the required structure."""
    print(f"✨ Creating new Google Sheet '{sheet_name}'...")
    spreadsheet = gc.create(sheet_name, folder_id=folder_id)
    spreadsheet.share(user_email, perm_type='user', role='writer')

    template_dfs = get_template_dataframes()
    sheet_order = ["Workflows", "Outputs", "Requests", "Prompts", "Models", "Workflow Steps", "Locations", "Eleven"]

    # Rename the initial "Sheet1" and populate it
    ws = spreadsheet.worksheet("Sheet1")
    ws.update_title(sheet_order[0])
    df = template_dfs.get(sheet_order[0])
    ws.update([df.columns.values.tolist()] + df.values.tolist())
    print(f"  - Created and formatted sheet: {sheet_order[0]}")

    # Add and populate the remaining sheets in the correct order
    for title in sheet_order[1:]:
        df = template_dfs.get(title)
        if df is not None:
            ws = spreadsheet.add_worksheet(title=title, rows=100, cols=30)
            ws.update([df.columns.values.tolist()] + df.values.tolist())
            print(f"  - Created and formatted sheet: {title}")

    print(f"✅ Google Sheet created and shared with {user_email}.")
    return spreadsheet


def connect_to_google_sheet():
    """Connects to Google Sheets using service account credentials."""
    scopes = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    return gspread.service_account(filename=GOOGLE_CREDS_JSON, scopes=scopes)

def try_load_google_sheet():
    try:
        gc = connect_to_google_sheet()
        try:
            spreadsheet = gc.open(GOOGLE_SHEET_NAME)
            ws = spreadsheet.worksheet("Workflows")
            headers = ws.row_values(1)
            if "Workflow Code" not in headers:
                print("⚠️ Old sheet structure detected. Archiving and creating a new one.")
                archive_name = f"{GOOGLE_SHEET_NAME} (Archived {int(time.time())})"
                gc.rename(spreadsheet, archive_name)
                print(f"  - Old sheet renamed to '{archive_name}'")
                spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)
        except gspread.exceptions.SpreadsheetNotFound:
            spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)
        return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in spreadsheet.worksheets()}
    except Exception as e:
        print(f"❌ Google Sheets not accessible: {e}")
        return None

# -----------------------------------------
# EXCEL FALLBACK STRUCTURE
# -----------------------------------------
def get_template_dataframes():
    """Returns a dictionary of DataFrames for the new simplified template structure."""
    workflow = pd.DataFrame([
        [1, "Generate Daily Script", "P1,P2&R1,P3&R2", "gpt-4o"],
        [2, "Test Daily News", "P1", "gpt-4o"],
        [3, "Test Daily News", "P1", "gpt-4o-mini"],
        [4, "Test Daily News", "P1M4", ""],
        [5, "Test Daily News", "P1M2", ""],
        [6, "Test Daily News", "P1M2,P2&R1M4", ""],
        [7, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2", ""],
        [8, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2,P4&R3M3", ""],
        [9, "Test Daily News", "P1M2,P2&R1M4,P3&R2M2,P4&R3M3,P5&R4M3", ""],
        [10, "Test Daily News and Script Save", "P1M2,P6&R1M2,P3&R2M2,P4&R3M3,P5&R4M3,R4SL7", ""],
        [11, "Send latest script to Eleven Labs", "L8E1SL4", ""],
        [12, "Combine intro mp3 with latest mp3 with outro mp3", "L1&L9&L2SL3", ""]
    ], columns=["Workflow ID", "Workflow Title", "Workflow Code", "Model Default"])

    outputs = pd.DataFrame(columns=[
        "Output ID", "Triggered Date", "Output 1", "Output 2", "Output 3", "Output 4", "Output 5", "Output 6", "Output 7", "Output 8", "Output 9", "Output 10"
    ])

    requests = pd.DataFrame([
        [1, 1, "", "N", ""],
        [2, 2, "", "N", ""],
        [3, 3, "", "N", "*used to work"],
        [4, 4, "", "N", "*works"],
        [5, 5, "", "N", "*works"],
        [6, 6, "", "N", "*works"],
        [7, 7, "", "N", "*works"],
        [8, 8, "", "N", "*works"],
        [9, 9, "", "N", "*works but some incorrect news stories"],
        [10, 10, "", "N", "*works outputs Script to folder"],
        [11, 11, "", "N", "*works to generate eleven labs based on latest file"],
        [12, 12, "", "Y", ""]
    ], columns=["Request ID", "Workflow ID", "Custom Topic If Required", "Active", "Comments"])

    prompts = pd.DataFrame([
        [1, "Daily News", "Please provide a comprehensive overview of the most important news in AI that occurred in the last 24-48 hours and mention dates of when the news items or recent updates occurred to confirm occurrence in the last 24-48 hours. AI news can be in relation to AI model releases, Expected tool releases, New enhancements released for AI tools or other interesting topics related to AI technology, AI company announcements, models, tool releases, enhancements, etc. Please be sure to summarize as many sources as possible and also provide numerous quotes from both company representatives, reporters as well as user feedback on social media."],
        [2, "Top 3 Topics", "Please select the top 3 news stories to generate podcast episodes on based on the top AI news stories below:"],
        [3, "Generate All On Appendend Topic", "Generate all details related to the news stories below from the last 24-48 hours. Please make sure to include any and all quotes from participants, companies or even social media reactions that have received significant engagement. Please also include technical specifications if required. Please ensure complete coverage provided details to ensure comprehensive coverage of story. Stories to retrieve all relevant details on:"]
    ], columns=["Prompt ID", "Prompt Title", "Prompt Description"])

    models = pd.DataFrame([
        [1, "gpt-4o", "N", "Y"],
        [2, "gpt-4o-mini", "N", "Y"],
        [3, "gpt-4o", "N", "N"],
        [4, "gpt-4o-mini", "Y", "N"],
        [5, "gpt-4o-mini-search-preview", "N", "Y"],
        [6, "gpt-4o-search-preview", "N", "Y"],
        [7, "chatgpt-4o-latest", "N", "N"],
        [8, "codex-mini-latest", "N", "N"],
        [9, "dall-e-2", "N", "N"],
        [10, "dall-e-3", "N", "N"],
        [11, "gpt-3.5-turbo-instruct", "N", "N"],
        [12, "gpt-4", "N", "N"],
        [13, "gpt-4.1", "N", "N"],
        [14, "gpt-4.1-mini", "N", "N"],
        [15, "gpt-4.1-mini-2025-04-14", "N", "N"],
        [16, "gpt-4.1-nano", "N", "N"],
        [17, "gpt-4.1-nano-2025-04-14", "N", "N"],
        [18, "gpt-4.5-preview", "N", "N"],
        [19, "gpt-4.5-preview-2025-02-27", "N", "N"],
        [20, "gpt-4o-audio-preview", "N", "N"],
        [21, "gpt-4o-mini-audio-preview", "N", "N"],
        [22, "gpt-4o-mini-search-preview", "N", "N"],
        [23, "gpt-4o-mini-search-preview-2025-03-11", "N", "N"],
        [24, "gpt-4o-mini-transcribe", "N", "N"],
        [25, "gpt-4o-mini-tts", "N", "N"],
        [26, "gpt-4o-realtime-preview", "N", "N"],
        [27, "gpt-4o-search-preview", "N", "N"],
        [28, "gpt-4o-search-preview-2025-03-11", "N", "N"],
        [29, "gpt-4o-transcribe", "N", "N"],
        [30, "gpt-image-1", "N", "N"],
        [31, "o1", "N", "N"],
        [32, "o1-mini", "N", "N"],
        [33, "o1-preview", "N", "N"],
        [34, "o1-pro", "N", "N"],
        [35, "o3-mini", "N", "N"],
        [36, "o3-mini-2025-01-31", "N", "N"],
        [37, "o4-mini", "N", "N"],
        [38, "omni-moderation-latest", "N", "N"],
        [39, "text-embedding-3-large", "N", "N"],
        [40, "text-embedding-3-small", "N", "N"],
        [41, "tts-1", "N", "N"],
        [42, "tts-1-1106", "N", "N"],
        [43, "tts-1-hd", "N", "N"],
        [44, "whisper-1", "N", "N"]
    ], columns=["Model ID", "Model Name", "Model Default", "Web Search"])

    workflow_steps = pd.DataFrame(columns=[
        "Workflow Steps ID", "Triggered Date", "Workflow ID", "Request ID", "Workflow Steps All", "Workflow Step", "Input", "Output", "Log Messages"
    ])

    locations = pd.DataFrame([
        [1, "Intro MP3 File", "File", "intro.mp3", "https://drive.google.com/file/d/1Q4DIYnk_E19_-2yqqm4j8ss8XplWXKd_/view?usp=drive_link"],
        [2, "Outro MP3 File", "File", "outro.mp3", "https://drive.google.com/file/d/1gbSFlbxpmgowth-bmngsSzoN1utT9sL2/view?usp=drive_link"],
        [3, "Podcast Folder Location", "Folder", "Podcasts/", "https://drive.google.com/drive/folders/1Vk-KziEUAVSIxL2_Sh5nCxySoZc_XBVj?usp=drive_link"],
        [4, "Eleven Labs Generated Audio", "Folder", "Podcasts/Eleven Labs/", "https://drive.google.com/drive/folders/167wtw8GA9-c6tfcplWy5b5SauL2MAuRR?usp=drive_link"],
        [5, "Latest MP3 File in Folder", "mp3", "Podcasts/", "https://drive.google.com/drive/folders/1Vk-KziEUAVSIxL2_Sh5nCxySoZc_XBVj?usp=drive_link"],
        [6, "Latest MP3 File in Folder", "mp3", "Podcasts/Eleven Labs/", "https://drive.google.com/drive/folders/167wtw8GA9-c6tfcplWy5b5SauL2MAuRR?usp=drive_link"],
        [7, "Scripts Folder Location", "Folder", "Scripts/", "https://drive.google.com/drive/folders/1KTGRQ3lkdTYNwkr_0UmG3bup6joj0oGn?usp=drive_link"],
        [8, "Latest Text File in Scripts Folder", "Text", "Scripts/", "https://drive.google.com/drive/folders/1KTGRQ3lkdTYNwkr_0UmG3bup6joj0oGn?usp=drive_link", "Y"],
        [9, "Latest mp3 in Eleven lab Folder", "mp3", "Podcasts/Eleven Labs/", "https://drive.google.com/drive/folders/167wtw8GA9-c6tfcplWy5b5SauL2MAuRR?usp=drive_link", "Y"]
    ], columns=["Location ID", "Location Description", "Type", "File Or Folder", "Location", "Latest"])

    eleven = pd.DataFrame([
        [1, "Liam", "eleven_multilingual_v2", 0.39, 0.7, 0.5, 1.06]
    ], columns=["Eleven ID", "Voice", "Model", "Stability", "Similarity Boost", "Style", "Speed"])

    return {
        "Workflows": workflow,
        "Outputs": outputs,
        "Requests": requests,
        "Prompts": prompts,
        "Models": models,
        "Workflow Steps": workflow_steps,
        "Locations": locations,
        "Eleven": eleven
    }


def generate_excel_template(file_path):
    template_dfs = get_template_dataframes()
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        for sheet_name, df in template_dfs.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    print(f"✅ Excel template created at: {file_path}")

# -----------------------------------------
# DATA LOADING FROM FILE OR GOOGLE
# -----------------------------------------
def load_workbook():
    data = try_load_google_sheet()
    if data:
        return data
    print("❌ Google Sheets not accessible. Please check your credentials, network, or sharing settings.")
    exit(1)

# -----------------------------------------
# UTILITY FUNCTIONS
# -----------------------------------------
def get_model_for_step(row, step_key, settings_df):
    override = row.get(f"Model: {step_key}")
    if override and str(override).strip():
        return override.strip()
    setting_map = {
        "Story Selection": "default_model_story_select",
        "Research": "default_model_research",
        "Script Gen": "default_model_script",
        "Title Desc": "default_model_title_desc"
    }
    setting_key = setting_map.get(step_key)
    value = settings_df.loc[settings_df['Setting Key'] == setting_key, 'Value']
    return value.values[0] if not value.empty else None

def get_intro_outro_paths(row, settings_df):
    base_path = settings_df.loc[settings_df['Setting Key'] == 'base_audio_folder_path', 'Value'].values[0]
    intro_file = row.get('Intro File Name') or settings_df.loc[settings_df['Setting Key'] == 'default_intro_file', 'Value'].values[0]
    outro_file = row.get('Outro File Name') or settings_df.loc[settings_df['Setting Key'] == 'default_outro_file', 'Value'].values[0]
    return os.path.join(base_path, intro_file), os.path.join(base_path, outro_file)

# -----------------------------------------
# API CALLS
# -----------------------------------------
def call_openai_model(prompt, model="gpt-4o", temperature=0.7, web_search=False):
    """Calls the OpenAI API, using the correct endpoint for web search and model type. Logs all errors and unexpected responses."""
    if not client.api_key:
        msg = "❌ OpenAI API key is not configured. Please check your .env file."
        log_error(msg)
        return ""
    try:
        # Case 1: Chat Completions with always-on search-preview model
        if web_search and (model.endswith("-search-preview")):
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                web_search_options={
                    "user_location": {"type": "approximate", "approximate": {"country": "US"}},
                    "search_context_size": "high"
                },
                temperature=temperature
            )
            # Robust error logging for chat completions
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI ChatCompletions error: {response.error}\nFull response: {response}")
                return ""
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content.strip()
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            return ""
        # Case 2: Responses API with web_search_preview tool (base models)
        elif web_search:
            if not hasattr(client, 'responses'):
                msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                log_error(msg)
                return "[Web search not supported by your OpenAI Python package version]"
            response = client.responses.create(
                model=model,
                tools=[{"type": "web_search_preview",
                        "search_context_size": "high",
                        "user_location": {"type": "approximate", "country": "US"}}],
                input=[{"role": "user",
                        "content": [{"type": "input_text", "text": prompt}]}],
                text={"format": {"type": "text"}}
            )
            # Robust error logging for responses.create
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI Responses error: {response.error}\nFull response: {response}")
                return ""
            try:
                for msg in getattr(response, 'output', []):
                    # Handle both dict and object
                    role = getattr(msg, 'role', None) or (msg.get('role') if isinstance(msg, dict) else None)
                    if role == "assistant":
                        content_list = getattr(msg, 'content', None) or (msg.get('content') if isinstance(msg, dict) else None)
                        if content_list:
                            for content in content_list:
                                # Handle both object and dict
                                ctype = getattr(content, 'type', None) or (content.get('type') if isinstance(content, dict) else None)
                                text = getattr(content, 'text', None) or (content.get('text') if isinstance(content, dict) else None)
                                if ctype == "output_text" and text:
                                    return text.strip()
                log_error(f"OpenAI Responses: Unexpected empty or malformed response. Full response: {response}")
                return ""
            except Exception as e:
                log_error(f"Error parsing OpenAI web search response: {e}\nRaw response: {response}")
                return ""
        # Case 3: Standard Chat Completions
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature
            )
            # Robust error logging for chat completions
            if hasattr(response, 'error') and response.error:
                log_error(f"OpenAI ChatCompletions error: {response.error}\nFull response: {response}")
                return ""
            if hasattr(response, 'choices') and response.choices:
                return response.choices[0].message.content.strip()
            log_error(f"OpenAI ChatCompletions: Unexpected empty or malformed response. Full response: {response}")
            return ""
    except Exception as e:
        log_error(f"OpenAI error: {e}")
        return ""

def split_text_into_chunks(text, max_length=2500):
    """
    Splits text into chunks of up to max_length characters, preferably on sentence boundaries.
    If a sentence is longer than max_length, it is split into hard chunks.
    """
    import re
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ''
    for sentence in sentences:
        # If the sentence itself is too long, split it hard
        while len(sentence) > max_length:
            part = sentence[:max_length]
            sentence = sentence[max_length:]
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ''
            chunks.append(part)
        if len(current_chunk) + len(sentence) + 1 <= max_length:
            current_chunk += (' ' if current_chunk else '') + sentence
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = sentence
    if current_chunk:
        chunks.append(current_chunk)
    print(f"[DEBUG] split_text_into_chunks: {len(chunks)} chunk(s) created.")
    for i, chunk in enumerate(chunks):
        print(f"[DEBUG]   Chunk {i+1} length: {len(chunk)}")
    return chunks

def generate_voice_audio(text, voice_id, output_path, eleven_config=None):
    """
    Enhanced Eleven Labs API call using the official Python client.
    Handles chunking for long texts and merges resulting audio files.
    Falls back to REST API if the client fails.
    """
    try:
        from elevenlabs.client import ElevenLabs
        
        # Split text into <=2500 character chunks
        chunks = split_text_into_chunks(text, max_length=2500)
        print(f"[DEBUG] generate_voice_audio: Preparing to send {len(chunks)} chunk(s) to Eleven Labs API.")
        if len(chunks) == 1:
            # Single chunk, process as before
            chunk_text = chunks[0]
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            if eleven_config:
                voice_settings = {
                    "stability": float(eleven_config.get('Stability', 0.39)),
                    "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                    "style": float(eleven_config.get('Style', 0.5)),
                    "speed": float(eleven_config.get('Speed', 1.06))
                }
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    if len(chunk_text) > 2000:
                        print(f"[WARNING] Chunk is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                    start_time = time.time()
                    audio_stream = client.text_to_speech.convert(
                        text=chunk_text,
                        voice_id=voice_id,
                        voice_settings=voice_settings,
                        model_id=eleven_config.get('Model', 'eleven_multilingual_v2')
                    )
                    elapsed = time.time() - start_time
                    print(f"[DEBUG] ElevenLabs SDK call returned in {elapsed:.3f}s (streaming)")
                    print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk. Saving to file...")
                except Exception as e:
                    print(f"❌ ElevenLabs client error: {e}")
                    traceback.print_exc()
                    print("[DEBUG] Falling back to REST API...")
                    return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
            else:
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    if len(chunk_text) > 2000:
                        print(f"[WARNING] Chunk is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                    start_time = time.time()
                    audio_stream = client.text_to_speech.convert(
                        text=chunk_text,
                        voice_id=voice_id,
                        model_id="eleven_multilingual_v2"
                    )
                    elapsed = time.time() - start_time
                    print(f"[DEBUG] ElevenLabs SDK call returned in {elapsed:.3f}s (streaming)")
                    print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk. Saving to file...")
                except Exception as e:
                    print(f"❌ ElevenLabs client error: {e}")
                    traceback.print_exc()
                    print("[DEBUG] Falling back to REST API...")
                    return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
            with open(output_path, 'wb') as f:
                for chunk in audio_stream:
                    f.write(chunk)
            print(f"✅ Audio generated successfully: {output_path}")
            return output_path
        else:
            # Multiple chunks: process each, then merge
            temp_audio_paths = []
            client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
            for idx, chunk_text in enumerate(chunks):
                print(f"[DEBUG] Sending chunk {idx+1}/{len(chunks)} to Eleven Labs API (length: {len(chunk_text)})")
                print(f"[DEBUG] Chunk {idx+1} preview: {chunk_text[:100]}")
                temp_path = f"{output_path}_chunk{idx+1}.mp3"
                if eleven_config:
                    voice_settings = {
                        "stability": float(eleven_config.get('Stability', 0.39)),
                        "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                        "style": float(eleven_config.get('Style', 0.5)),
                        "speed": float(eleven_config.get('Speed', 1.06))
                    }
                    try:
                        print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                        if len(chunk_text) > 2000:
                            print(f"[WARNING] Chunk {idx+1} is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                        start_time = time.time()
                        audio_stream = client.text_to_speech.convert(
                            text=chunk_text,
                            voice_id=voice_id,
                            voice_settings=voice_settings,
                            model_id=eleven_config.get('Model', 'eleven_multilingual_v2')
                        )
                        elapsed = time.time() - start_time
                        print(f"[DEBUG] ElevenLabs SDK call for chunk {idx+1} returned in {elapsed:.3f}s (streaming)")
                        print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk {idx+1}. Saving to file...")
                    except Exception as e:
                        print(f"[ERROR] Failed on chunk {idx+1}/{len(chunks)}. First 100 chars: {chunk_text[:100]}")
                        traceback.print_exc()
                        print("[DEBUG] Falling back to REST API...")
                        for p in temp_audio_paths:
                            try: os.remove(p)
                            except: pass
                        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
                else:
                    try:
                        print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                        if len(chunk_text) > 2000:
                            print(f"[WARNING] Chunk {idx+1} is very long ({len(chunk_text)} chars). Consider splitting further if you see timeouts.")
                        start_time = time.time()
                        audio_stream = client.text_to_speech.convert(
                            text=chunk_text,
                            voice_id=voice_id,
                            model_id="eleven_multilingual_v2"
                        )
                        elapsed = time.time() - start_time
                        print(f"[DEBUG] ElevenLabs SDK call for chunk {idx+1} returned in {elapsed:.3f}s (streaming)")
                        print(f"[DEBUG] ElevenLabs SDK: Received audio stream for chunk {idx+1}. Saving to file...")
                    except Exception as e:
                        print(f"[ERROR] Failed on chunk {idx+1}/{len(chunks)}. First 100 chars: {chunk_text[:100]}")
                        traceback.print_exc()
                        print("[DEBUG] Falling back to REST API...")
                        for p in temp_audio_paths:
                            try: os.remove(p)
                            except: pass
                        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
                with open(temp_path, 'wb') as f:
                    for chunk in audio_stream:
                        f.write(chunk)
                print(f"✅ Audio chunk {idx+1} generated and saved: {temp_path}")
                temp_audio_paths.append(temp_path)
            # Merge all chunk audio files
            merged_path = merge_multiple_audio_files(temp_audio_paths, output_path)
            # Clean up temp chunk files
            for p in temp_audio_paths:
                try: os.remove(p)
                except: pass
            if merged_path:
                print(f"✅ Audio generated and merged successfully: {merged_path}")
            return merged_path
    except ImportError:
        print("⚠️ ElevenLabs Python client not installed. Falling back to REST API...")
        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)
    except Exception as e:
        print(f"❌ ElevenLabs error: {e}")
        traceback.print_exc()
        print("[DEBUG] Falling back to REST API...")
        return generate_voice_audio_rest(text, voice_id, output_path, eleven_config)


def generate_voice_audio_rest(text, voice_id, output_path, eleven_config=None):
    """Fallback REST API method for Eleven Labs. Handles chunking and merging."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    
    def _single_chunk(chunk_text, temp_path):
        if eleven_config:
            payload = {
                "text": chunk_text,
                "model_id": eleven_config.get('Model', 'eleven_multilingual_v2'),
                "voice_settings": {
                    "stability": float(eleven_config.get('Stability', 0.39)),
                    "similarity_boost": float(eleven_config.get('Similarity Boost', 0.7)),
                    "style": float(eleven_config.get('Style', 0.5)),
                    "speed": float(eleven_config.get('Speed', 1.06))
                }
            }
        else:
            payload = {
                "text": chunk_text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.7
                }
            }
        try:
            print(f"[DEBUG] ElevenLabs API payload: {json.dumps(payload)[:500]}{'...' if len(json.dumps(payload)) > 500 else ''}")
            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=120)
            elapsed = time.time() - start_time
            print(f"[DEBUG] ElevenLabs API call took {elapsed:.2f} seconds")
            print(f"[DEBUG] ElevenLabs REST API response status: {response.status_code}")
            print(f"[DEBUG] ElevenLabs REST API response headers: {dict(response.headers)}")
            if response.status_code == 200:
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Audio chunk received and saved: {temp_path}")
                return temp_path
            else:
                print(f"❌ ElevenLabs REST API error: {response.status_code} {response.text}")
                # Try to print error message from JSON if available
                try:
                    error_json = response.json()
                    if 'error' in error_json:
                        print(f"❌ ElevenLabs API error message: {error_json['error']}")
                    else:
                        print(f"❌ ElevenLabs API error JSON: {error_json}")
                except Exception:
                    print(f"❌ ElevenLabs API error (non-JSON): {response.content[:500]}")
                return None
        except requests.exceptions.Timeout:
            print("❌ ElevenLabs REST API error: Request timed out after 120 seconds.")
            traceback.print_exc()
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ ElevenLabs REST API error: {e}")
            traceback.print_exc()
            if hasattr(e, 'response') and e.response is not None:
                print(f"❌ ElevenLabs REST API error response: {e.response.text}")
            return None
        except Exception as e:
            print(f"❌ ElevenLabs REST API error: {e}")
            traceback.print_exc()
            return None

    # Split text into <=2500 character chunks
    chunks = split_text_into_chunks(text, max_length=2500)
    if len(chunks) == 1:
        return _single_chunk(chunks[0], output_path)
    else:
        temp_audio_paths = []
        for idx, chunk_text in enumerate(chunks):
            temp_path = f"{output_path}_chunk{idx+1}.mp3"
            result = _single_chunk(chunk_text, temp_path)
            if result:
                temp_audio_paths.append(result)
            else:
                # Clean up any previous temp files
                for p in temp_audio_paths:
                    try: os.remove(p)
                    except: pass
                return None
        merged_path = merge_multiple_audio_files(temp_audio_paths, output_path)
        for p in temp_audio_paths:
            try: os.remove(p)
            except: pass
        if merged_path:
            print(f"✅ Audio generated and merged successfully: {merged_path}")
        return merged_path

def download_latest_text_file_from_drive(service_account_json, folder_id):
    """Downloads the latest text file from a Google Drive folder."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_json, 
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build('drive', 'v3', credentials=creds)
        
        # List files in the folder, sorted by modified time (newest first)
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType='text/plain'",
            orderBy='modifiedTime desc',
            pageSize=1,
            fields='files(id,name,modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        if not files:
            print(f"❌ No text files found in folder {folder_id}")
            return None
            
        latest_file = files[0]
        file_id = latest_file['id']
        file_name = latest_file['name']
        
        print(f"📥 Downloading latest text file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        content = fh.getvalue().decode('utf-8')
        print(f"✅ Downloaded {len(content)} characters from {file_name}")
        return content
        
    except Exception as e:
        print(f"❌ Error downloading file from Google Drive: {e}")
        return None

def upload_audio_to_drive(service_account_json, folder_id, filename, audio_file_path):
    """Uploads an audio file to Google Drive folder and returns the file link."""
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from google.oauth2 import service_account
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_json, 
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build('drive', 'v3', credentials=creds)
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'audio/mpeg'
        }
        
        media = MediaFileUpload(audio_file_path, mimetype='audio/mpeg')
        file = drive_service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id,webViewLink'
        ).execute()
        
        return file.get('webViewLink')
        
    except Exception as e:
        print(f"❌ Error uploading audio to Google Drive: {e}")
        return None

def merge_audio(intro_path, main_path, outro_path, final_path):
    try:
        intro = AudioSegment.from_file(intro_path)
        main = AudioSegment.from_file(main_path)
        outro = AudioSegment.from_file(outro_path)
        final = intro + main + outro
        final.export(final_path, format="mp3")
        print(f"✅ Merged audio saved: {final_path}")
    except Exception as e:
        print(f"❌ Merge failed: {e}")

def download_latest_mp3_from_drive(service_account_json, folder_id):
    """Downloads the latest MP3 file from a Google Drive folder."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        creds = service_account.Credentials.from_service_account_file(
            service_account_json, 
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build('drive', 'v3', credentials=creds)
        
        # List MP3 files in the folder, sorted by modified time (newest first)
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and mimeType='audio/mpeg'",
            orderBy='modifiedTime desc',
            pageSize=1,
            fields='files(id,name,modifiedTime)'
        ).execute()
        
        files = results.get('files', [])
        if not files:
            print(f"❌ No MP3 files found in folder {folder_id}")
            return None
            
        latest_file = files[0]
        file_id = latest_file['id']
        file_name = latest_file['name']
        
        print(f"📥 Downloading latest MP3 file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        # Save to temporary file
        temp_path = f"temp_{file_name}"
        with open(temp_path, 'wb') as f:
            f.write(fh.getvalue())
        
        print(f"✅ Downloaded MP3 file: {temp_path}")
        return temp_path
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from Google Drive: {e}")
        return None

def download_mp3_file_from_drive(service_account_json, file_url):
    """Downloads a specific MP3 file from Google Drive using its URL."""
    from googleapiclient.discovery import build
    from google.oauth2 import service_account
    from googleapiclient.http import MediaIoBaseDownload
    import io
    
    try:
        # Extract file ID from Google Drive URL
        file_id_match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', file_url)
        if not file_id_match:
            print(f"❌ Invalid Google Drive file URL: {file_url}")
            return None
        
        file_id = file_id_match.group(1)
        
        creds = service_account.Credentials.from_service_account_file(
            service_account_json, 
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build('drive', 'v3', credentials=creds)
        
        # Get file metadata
        file_metadata = drive_service.files().get(fileId=file_id, fields='name').execute()
        file_name = file_metadata.get('name', 'unknown_file.mp3')
        
        print(f"📥 Downloading MP3 file: {file_name}")
        
        # Download the file content
        request = drive_service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while done is False:
            status, done = downloader.next_chunk()
            if status:
                print(f"  Download {int(status.progress() * 100)}%")
        
        # Save to temporary file
        temp_path = f"temp_{file_name}"
        with open(temp_path, 'wb') as f:
            f.write(fh.getvalue())
        
        print(f"✅ Downloaded MP3 file: {temp_path}")
        return temp_path
        
    except Exception as e:
        print(f"❌ Error downloading MP3 from Google Drive: {e}")
        return None

def merge_multiple_audio_files(audio_paths, output_path):
    """Merges multiple audio files into a single MP3 file."""
    try:
        if not audio_paths:
            print("❌ No audio files provided for merging")
            return None
        
        print(f"🔗 Merging {len(audio_paths)} audio files...")
        
        # Load the first audio file
        combined = AudioSegment.from_file(audio_paths[0])
        print(f"  - Loaded: {audio_paths[0]}")
        
        # Add subsequent audio files
        for i, audio_path in enumerate(audio_paths[1:], 1):
            audio = AudioSegment.from_file(audio_path)
            combined += audio
            print(f"  - Added: {audio_path}")
        
        # Export the combined audio
        combined.export(output_path, format="mp3")
        print(f"✅ Merged audio saved: {output_path}")
        return output_path
        
    except Exception as e:
        print(f"❌ Error merging audio files: {e}")
        return None

# -----------------------------------------
# MAIN EXECUTION
# -----------------------------------------
if __name__ == '__main__':
    print("🚀 Starting AI Workflow Pipeline")

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    print("✅ Workbook loaded. Starting workflow processing...")
    gc = connect_to_google_sheet()
    spreadsheet = gc.open(GOOGLE_SHEET_NAME)
    workflow_ws = spreadsheet.worksheet("Workflows")
    outputs_ws = spreadsheet.worksheet("Outputs")
    requests_ws = spreadsheet.worksheet("Requests")
    prompts_ws = spreadsheet.worksheet("Prompts")
    models_ws = spreadsheet.worksheet("Models")
    workflow_steps_ws = spreadsheet.worksheet("Workflow Steps")
    locations_ws = spreadsheet.worksheet("Locations")

    # Try to load Eleven tab (may not exist in older sheets)
    eleven_ws = None
    try:
        eleven_ws = spreadsheet.worksheet("Eleven")
    except Exception:
        pass  # If the Eleven tab doesn't exist, skip it

    workflow_df = pd.DataFrame(workflow_ws.get_all_records())
    outputs_df = pd.DataFrame(outputs_ws.get_all_records())
    requests_df = pd.DataFrame(requests_ws.get_all_records())
    prompts_df = pd.DataFrame(prompts_ws.get_all_records())
    models_df = pd.DataFrame(models_ws.get_all_records())
    workflow_steps_df = pd.DataFrame(workflow_steps_ws.get_all_records())
    locations_df = pd.DataFrame(locations_ws.get_all_records()) if locations_ws is not None else pd.DataFrame(columns=["Location ID", "Location Description", "Type", "File Or Folder", "Location", "Latest"])
    eleven_df = pd.DataFrame(eleven_ws.get_all_records()) if eleven_ws is not None else pd.DataFrame(columns=["Eleven ID", "Voice", "Model", "Stability", "Similarity Boost", "Style", "Speed"])

    logs_ws = None
    try:
        logs_ws = spreadsheet.worksheet("Logs")
    except Exception:
        pass  # If the Logs tab doesn't exist, skip logging

    logs_df = pd.DataFrame(logs_ws.get_all_records()) if logs_ws else pd.DataFrame(columns=["Log ID", "Log Timestamp", "Log Message"])

    def get_next_log_id():
        if logs_df.empty or 'Log ID' not in logs_df.columns:
            return 1
        return int(logs_df['Log ID'].astype(int).max()) + 1

    def log_error(message):
        if logs_ws is not None:
            log_row = [get_next_log_id(), pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S'), str(message)]
            logs_ws.append_row(log_row)
        print(f"[LOGGED ERROR] {message}")

    # Helper to get next Output ID
    def get_next_output_id():
        if outputs_df.empty:
            return 1
        return outputs_df['Output ID'].astype(int).max() + 1

    # Helper to get next Workflow Steps ID
    def get_next_workflow_steps_id():
        if workflow_steps_df.empty:
            return 1
        return workflow_steps_df['Workflow Steps ID'].astype(int).max() + 1

    # Helper to get model name by Model ID
    def get_model_name(model_id):
        row = models_df[models_df['Model ID'].astype(str) == str(model_id)]
        if not row.empty:
            return row.iloc[0]['Model Name']
        return None

    # Helper to get Model ID by model name (returns the first match)
    def get_model_id_by_name(model_name):
        row = models_df[models_df['Model Name'] == model_name]
        if not row.empty:
            return str(row.iloc[0]['Model ID'])
        return None

    # Helper to get web search flag for a model by Model ID
    def get_model_web_search_by_id(model_id):
        row = models_df[models_df['Model ID'].astype(str) == str(model_id)]
        if not row.empty:
            return str(row.iloc[0].get('Web Search', 'N')).strip().upper() == 'Y'
        return False

    # Helper to get web search flag for a model by name (first match)
    def get_model_web_search_by_name(model_name):
        row = models_df[models_df['Model Name'] == model_name]
        if not row.empty:
            return str(row.iloc[0].get('Web Search', 'N')).strip().upper() == 'Y'
        return False

    # Helper to get prompt description by Prompt ID
    def get_prompt_desc(prompt_id):
        row = prompts_df[prompts_df['Prompt ID'].astype(str) == str(prompt_id)]
        if not row.empty:
            return row.iloc[0]['Prompt Description']
        return None

    # Helper to get default model for workflow
    def get_workflow_default_model(workflow_row):
        return workflow_row['Model Default'] if 'Model Default' in workflow_row else 'gpt-4o'

    # Helper to extract Google Drive folder ID from URL
    def extract_drive_folder_id(url):
        match = re.search(r"/folders/([a-zA-Z0-9_-]+)", url)
        if match:
            return match.group(1)
        return None

    # Helper to upload a text file to Google Drive folder and return the file link
    def upload_text_to_drive(service_account_json, folder_id, filename, text):
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        from google.oauth2 import service_account
        creds = service_account.Credentials.from_service_account_file(service_account_json, scopes=["https://www.googleapis.com/auth/drive"])
        drive_service = build('drive', 'v3', credentials=creds)
        file_metadata = {
            'name': filename,
            'parents': [folder_id],
            'mimeType': 'text/plain'
        }
        media = MediaInMemoryUpload(text.encode('utf-8'), mimetype='text/plain')
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id,webViewLink').execute()
        return file.get('webViewLink')

    # Helper to get Eleven Labs configuration by Eleven ID
    def get_eleven_config(eleven_id):
        row = eleven_df[eleven_df['Eleven ID'].astype(str) == str(eleven_id)]
        if not row.empty:
            return row.iloc[0].to_dict()
        return None

    # Helper to get voice ID by Eleven ID (this would need to be configured based on your Eleven Labs voice IDs)
    def get_voice_id_by_eleven_id(eleven_id):
        # This mapping should be updated with your actual Eleven Labs voice IDs
        voice_mapping = {
            "1": "TX3LPaxmHKxFdv7VOQHJ",  # Liam voice ID from Eleven Labs
            # Add more mappings as needed
        }
        return voice_mapping.get(str(eleven_id))

    # Helper to get location by Location ID
    def get_location_by_id(location_id):
        row = locations_df[locations_df['Location ID'].astype(str) == str(location_id)]
        if not row.empty:
            return row.iloc[0].to_dict()
        return None

    # Parse workflow code step (e.g. P2&R1M8)
    def parse_step(step, prev_outputs, custom_topic):
        # Find model override (M#)
        model_override = None
        model_id_override = None
        m_match = re.search(r'M(\d+)', step)
        if m_match:
            model_id_override = m_match.group(1)
            model_override = get_model_name(model_id_override)
            step = re.sub(r'M\d+', '', step)
        # Split by & for combining
        parts = [p.strip() for p in step.split('&')]
        input_text = ''
        for part in parts:
            if part.startswith('P'):
                prompt_id = part[1:]
                input_text += get_prompt_desc(prompt_id) or ''
            elif part.startswith('R'):
                # Extract only the leading digits after 'R'
                match = re.match(r'R(\d+)', part)
                if match:
                    resp_idx = int(match.group(1)) - 1
                    if 0 <= resp_idx < len(prev_outputs):
                        input_text += prev_outputs[resp_idx]
            elif part == 'C':
                input_text += custom_topic or ''
        return input_text, model_override, model_id_override

    # Main workflow loop
    for req_idx, req_row in requests_df.iterrows():
        if str(req_row.get('Active', '')).strip().upper() != 'Y':
            continue
        request_id = req_row['Request ID']
        workflow_id = req_row['Workflow ID']
        custom_topic = req_row.get('Custom Topic If Required', '')
        print(f"\n🔔 Processing Request ID {request_id} for Workflow ID {workflow_id}")
        workflow_row = workflow_df[workflow_df['Workflow ID'] == workflow_id]
        if workflow_row.empty:
            print(f"  - ⚠ Workflow ID {workflow_id} not found.")
            continue
        workflow_row = workflow_row.iloc[0]
        workflow_code = workflow_row['Workflow Code']
        default_model = get_workflow_default_model(workflow_row)
        default_model_id = get_model_id_by_name(default_model)
        steps = [s.strip() for s in workflow_code.split(',') if s.strip()]
        prev_outputs = []
        workflow_steps_records = []
        output_record = {
            'Output ID': get_next_output_id(),
            'Triggered Date': pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        for i, step in enumerate(steps):
            # Check for save-only step (e.g., R4SL7)
            save_only_match = re.fullmatch(r'R(\d+)SL(\d+)', step)
            if save_only_match:
                print(f"  - Step {i+1}: {step} (Save-Only Step)")
                resp_idx = int(save_only_match.group(1)) - 1
                location_id = save_only_match.group(2)
                response_to_save = None
                log_msg = ''
                if 0 <= resp_idx < len(prev_outputs):
                    response_to_save = prev_outputs[resp_idx]
                    loc_row = locations_df[locations_df['Location ID'].astype(str) == location_id]
                    if not loc_row.empty:
                        folder_url = loc_row.iloc[0]['Location']
                        folder_id = extract_drive_folder_id(folder_url)
                        if folder_id:
                            filename = f'workflow_{request_id}_step_{i+1}.txt'
                            try:
                                file_link = upload_text_to_drive(GOOGLE_CREDS_JSON, folder_id, filename, response_to_save)
                                log_msg = f"Saved response to Google Drive: {file_link}"
                            except Exception as e:
                                log_msg = f"Failed to save response to Google Drive: {e}"
                        else:
                            log_msg = f"Invalid Google Drive folder ID for location {location_id}."
                    else:
                        log_msg = f"Location ID {location_id} not found in Locations sheet."
                else:
                    log_msg = f"Response index {resp_idx+1} not found in previous outputs."
                
                print(f"    > {log_msg}")

                # Always append a workflow step record for save-only steps
                workflow_steps_records.append([
                    get_next_workflow_steps_id() + i + 0.1,  # fractional ID to keep order
                    output_record['Triggered Date'],
                    workflow_id,
                    request_id,
                    workflow_code,
                    step,
                    response_to_save if response_to_save is not None else '',
                    '',  # No new output
                    log_msg
                ])
                # Only append to prev_outputs if response_to_save is defined
                if response_to_save is not None:
                    prev_outputs.append(response_to_save)
                continue  # Skip model call for this step
            
            # Check for Eleven Labs step (e.g., L8E1SL4)
            eleven_match = re.fullmatch(r'L(\d+)E(\d+)SL(\d+)', step)
            if eleven_match:
                print(f"  - Step {i+1}: {step} (Eleven Labs Step)")
                location_id = eleven_match.group(1)
                eleven_id = eleven_match.group(2)
                save_location_id = eleven_match.group(3)
                
                # Get location details for source folder
                source_location = get_location_by_id(location_id)
                if not source_location:
                    log_msg = f"Source location ID {location_id} not found in Locations sheet."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Get Eleven Labs configuration
                eleven_config = get_eleven_config(eleven_id)
                if not eleven_config:
                    log_msg = f"Eleven Labs configuration ID {eleven_id} not found in Eleven sheet."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Get voice ID
                voice_id = get_voice_id_by_eleven_id(eleven_id)
                if not voice_id:
                    log_msg = f"Voice ID not found for Eleven ID {eleven_id}. Please update voice_mapping in get_voice_id_by_eleven_id function."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Download latest text file from source location
                source_folder_url = source_location['Location']
                source_folder_id = extract_drive_folder_id(source_folder_url)
                if not source_folder_id:
                    log_msg = f"Invalid Google Drive folder ID for source location {location_id}."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                text_content = download_latest_text_file_from_drive(GOOGLE_CREDS_JSON, source_folder_id)
                if not text_content:
                    log_msg = f"Failed to download text file from source location {location_id}."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Generate audio using Eleven Labs
                print(f"    > Generating audio with voice: {eleven_config['Voice']}")
                temp_audio_path = f'temp_audio_{request_id}_step_{i+1}.mp3'
                audio_path = generate_voice_audio(text_content, voice_id, temp_audio_path, eleven_config)
                
                if not audio_path:
                    log_msg = f"Failed to generate audio with Eleven Labs for step {i+1}. Aborting workflow."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        text_content,
                        '',
                        log_msg
                    ])
                    # End the entire workflow immediately
                    print("[FATAL] Eleven Labs API error encountered. Exiting workflow.")
                    sys.exit(1)
                
                # Upload audio to destination location
                save_location = get_location_by_id(save_location_id)
                if not save_location:
                    log_msg = f"Save location ID {save_location_id} not found in Locations sheet."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        text_content,
                        audio_path,
                        log_msg
                    ])
                    continue
                
                save_folder_url = save_location['Location']
                save_folder_id = extract_drive_folder_id(save_folder_url)
                if not save_folder_id:
                    log_msg = f"Invalid Google Drive folder ID for save location {save_location_id}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        text_content,
                        audio_path,
                        log_msg
                    ])
                    continue
                
                audio_filename = f'workflow_{request_id}_step_{i+1}_{eleven_config["Voice"]}.mp3'
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    start_time = time.time()
                    file_link = upload_audio_to_drive(GOOGLE_CREDS_JSON, save_folder_id, audio_filename, audio_path)
                    log_msg = f"Generated and uploaded audio to Google Drive: {file_link}"
                    print(f"    > {log_msg}")
                except Exception as e:
                    log_msg = f"Failed to upload audio to Google Drive: {e}"
                    print(f"    > {log_msg}")
                
                # Clean up temporary file
                try:
                    os.remove(temp_audio_path)
                except:
                    pass
                
                # Add workflow step record
                workflow_steps_records.append([
                    get_next_workflow_steps_id() + i + 0.1,
                    output_record['Triggered Date'],
                    workflow_id,
                    request_id,
                    workflow_code,
                    step,
                    text_content,
                    audio_path,
                    log_msg
                ])
                
                # Add audio path to outputs
                prev_outputs.append(audio_path)
                continue  # Skip regular model call for this step
            
            # Check for Audio Merging step (e.g., L1&L9&L2SL3)
            audio_merge_match = re.fullmatch(r'L(\d+)(?:&L(\d+))*SL(\d+)', step)
            if audio_merge_match:
                print(f"  - Step {i+1}: {step} (Audio Merging Step)")
                
                # Extract all location IDs from the step
                location_ids = re.findall(r'L(\d+)', step)
                save_location_id = location_ids[-1]  # Last location ID is the save location
                source_location_ids = location_ids[:-1]  # All others are source locations
                
                if len(source_location_ids) < 2:
                    log_msg = f"Audio merging requires at least 2 source locations, found {len(source_location_ids)}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Download audio files from source locations
                audio_paths = []
                download_errors = []
                
                for loc_id in source_location_ids:
                    location = get_location_by_id(loc_id)
                    if not location:
                        error_msg = f"Location ID {loc_id} not found in Locations sheet."
                        download_errors.append(error_msg)
                        continue
                    
                    location_url = location['Location']
                    location_type = location['Type']
                    
                    if location_type == 'File':
                        # Download specific file
                        audio_path = download_mp3_file_from_drive(GOOGLE_CREDS_JSON, location_url)
                    elif location_type == 'mp3':
                        # Download latest MP3 from folder
                        folder_id = extract_drive_folder_id(location_url)
                        if folder_id:
                            audio_path = download_latest_mp3_from_drive(GOOGLE_CREDS_JSON, folder_id)
                        else:
                            error_msg = f"Invalid Google Drive folder ID for location {loc_id}"
                            download_errors.append(error_msg)
                            continue
                    else:
                        error_msg = f"Location {loc_id} is not a file or mp3 type"
                        download_errors.append(error_msg)
                        continue
                    
                    if audio_path:
                        audio_paths.append(audio_path)
                    else:
                        error_msg = f"Failed to download audio from location {loc_id}"
                        download_errors.append(error_msg)
                
                if download_errors:
                    log_msg = f"Audio download errors: {'; '.join(download_errors)}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                if len(audio_paths) < 2:
                    log_msg = f"Not enough audio files downloaded for merging. Expected at least 2, got {len(audio_paths)}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        '',
                        '',
                        log_msg
                    ])
                    continue
                
                # Merge audio files
                print(f"    > Merging {len(audio_paths)} audio files...")
                merged_audio_path = f'merged_audio_{request_id}_step_{i+1}.mp3'
                merged_path = merge_multiple_audio_files(audio_paths, merged_audio_path)
                
                if not merged_path:
                    log_msg = f"Failed to merge audio files for step {i+1}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        str(audio_paths),
                        '',
                        log_msg
                    ])
                    continue
                
                # Upload merged audio to destination location
                save_location = get_location_by_id(save_location_id)
                if not save_location:
                    log_msg = f"Save location ID {save_location_id} not found in Locations sheet."
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        str(audio_paths),
                        merged_path,
                        log_msg
                    ])
                    continue
                
                save_folder_url = save_location['Location']
                save_folder_id = extract_drive_folder_id(save_folder_url)
                if not save_folder_id:
                    log_msg = f"Invalid Google Drive folder ID for save location {save_location_id}"
                    print(f"    > {log_msg}")
                    workflow_steps_records.append([
                        get_next_workflow_steps_id() + i + 0.1,
                        output_record['Triggered Date'],
                        workflow_id,
                        request_id,
                        workflow_code,
                        step,
                        str(audio_paths),
                        merged_path,
                        log_msg
                    ])
                    continue
                
                audio_filename = f'merged_workflow_{request_id}_step_{i+1}.mp3'
                try:
                    print(f"[DEBUG] Using model: {eleven_config.get('Model', 'eleven_multilingual_v2') if eleven_config else 'eleven_multilingual_v2'}, voice_id: {voice_id}")
                    start_time = time.time()
                    file_link = upload_audio_to_drive(GOOGLE_CREDS_JSON, save_folder_id, audio_filename, merged_path)
                    log_msg = f"Merged and uploaded audio to Google Drive: {file_link}"
                    print(f"    > {log_msg}")
                except Exception as e:
                    log_msg = f"Failed to upload merged audio to Google Drive: {e}"
                    print(f"    > {log_msg}")
                
                # Clean up temporary files
                for temp_path in audio_paths:
                    try:
                        os.remove(temp_path)
                    except:
                        pass
                
                # Add workflow step record
                workflow_steps_records.append([
                    get_next_workflow_steps_id() + i + 0.1,
                    output_record['Triggered Date'],
                    workflow_id,
                    request_id,
                    workflow_code,
                    step,
                    str(audio_paths),
                    merged_path,
                    log_msg
                ])
                
                # Add merged audio path to outputs
                prev_outputs.append(merged_path)
                continue  # Skip regular model call for this step
            
            # Parse the step for prompt, model override, and model ID override
            input_text, model_override, model_id_override = parse_step(step, prev_outputs, custom_topic)
            if model_override and model_id_override:
                model_to_use = model_override
                web_search_enabled = get_model_web_search_by_id(model_id_override)
            else:
                model_to_use = default_model
                web_search_enabled = get_model_web_search_by_id(default_model_id)
            print(f"  - Step {i+1}: {step} (Model: {model_to_use}, Web Search: {web_search_enabled})")
            print(f"    Input: {input_text[:100]}{'...' if len(input_text) > 100 else ''}")
            # Fallback for OpenAI client if responses.create is not available
            if web_search_enabled and not hasattr(client, 'responses'):
                msg = "❌ Web search requested but your OpenAI Python package does not support responses.create. Please upgrade openai to the latest version."
                log_error(msg)
                response = "[Web search not supported by your OpenAI Python package version]"
            else:
                response = call_openai_model(input_text, model_to_use, web_search=web_search_enabled)
            prev_outputs.append(response)
            output_col_in = f'Output {2*i+1}'
            output_col_out = f'Output {2*i+2}'
            output_record[output_col_in] = input_text
            output_record[output_col_out] = response
            # Check for SL# pattern in step (e.g., R4SL7)
            sl_match = re.search(r'SL(\d+)', step)
            if sl_match:
                location_id = sl_match.group(1)
                loc_row = locations_df[locations_df['Location ID'].astype(str) == location_id]
                if not loc_row.empty:
                    folder_url = loc_row.iloc[0]['Location']
                    folder_id = extract_drive_folder_id(folder_url)
                    if folder_id:
                        filename = f'workflow_{request_id}_step_{i+1}.txt'
                        try:
                            file_link = upload_text_to_drive(GOOGLE_CREDS_JSON, folder_id, filename, response)
                            log_msg = f"Saved response to Google Drive: {file_link}"
                        except Exception as e:
                            log_msg = f"Failed to save response to Google Drive: {e}"
                        # Add file link or error to Workflow Steps log message
                        workflow_steps_records.append([
                            get_next_workflow_steps_id() + i + 0.1,  # fractional ID to keep order
                            output_record['Triggered Date'],
                            workflow_id,
                            request_id,
                            workflow_code,
                            step,
                            input_text,
                            response,
                            log_msg
                        ])
        # Write to Outputs tab
        def to_native(val):
            if hasattr(val, 'item'):
                return val.item()
            if isinstance(val, (int, float, str)) or val is None:
                return val
            return str(val)

        output_row = [to_native(output_record.get(col, '')) for col in outputs_df.columns]
        outputs_ws.append_row(output_row)
        # Write to Workflow Steps tab
        for ws_row in workflow_steps_records:
            ws_row_native = [to_native(x) for x in ws_row]
            workflow_steps_ws.append_row(ws_row_native)
        # Mark request as processed (disabled per user request)
        # requests_ws.update_cell(req_idx + 2, requests_df.columns.get_loc('Active') + 1, 'N')
        print(f"✅ Request {request_id} processed and logged.")