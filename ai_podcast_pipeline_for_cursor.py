import os
import pandas as pd
import gspread
import requests
import openai
from pydub import AudioSegment
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'path/to/your/credentials.json'
GOOGLE_SHEET_NAME = 'AI Podcast Workflow'
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-key')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', 'your-elevenlabs-key')

# -----------------------------------------
# GOOGLE SHEET SUPPORT
# -----------------------------------------
def connect_to_google_sheet(sheet_name):
    credentials = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_JSON, [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ])
    gc = gspread.authorize(credentials)
    return gc.open(sheet_name)

def try_load_google_sheet():
    try:
        spreadsheet = connect_to_google_sheet(GOOGLE_SHEET_NAME)
        return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in spreadsheet.worksheets()}
    except Exception as e:
        print(f"⚠ Google Sheets not accessible: {e}")
        return None

# -----------------------------------------
# EXCEL FALLBACK STRUCTURE
# -----------------------------------------
def generate_excel_template(file_path):
    episode_tracker = pd.DataFrame(columns=[
        "Episode ID", "Episode Date", "Type", "Topic Title", "Manual Prompt",
        "Model: Story Selection", "Model: Research", "Model: Script Gen", "Model: Title Desc",
        "Intro File Name", "Outro File Name",
        "Story 1 Title", "Story 2 Title", "Story 3 Title",
        "Research 1", "Research 2", "Research 3",
        "Script", "Episode Title", "Episode Description",
        "Audio File URL", "Status", "Error Log"
    ])
    manual_ideas = pd.DataFrame(columns=[
        "ID", "Episode Title (Idea)", "Topic Prompt",
        "Model: Research", "Model: Script",
        "Intro File Name", "Outro File Name",
        "Expanded Research", "Script Generated?", "Final Script", "Episode Ready?"
    ])
    prompts_used = pd.DataFrame(columns=[
        "Prompt Step", "Model Used", "Prompt Text", "Tokens Used", "Cost (USD)", "Timestamp"
    ])
    settings_data = [
        ["default_model_story_select", "gpt-4o"],
        ["default_model_research", "gpt-4o"],
        ["default_model_script", "gpt-4o"],
        ["default_model_title_desc", "claude-3-haiku"],
        ["base_audio_folder_path", "C:/podcast/audio_assets/"],
        ["default_intro_file", "intro_default.mp3"],
        ["default_outro_file", "outro_default.mp3"],
        ["upload_folder_id", "drive-folder-xyz123"],
        ["daily_trigger_time", "07:00 EST"],
        ["elevenlabs_voice_id", "21m00Tcm4TlvDq8ikWAM"]
    ]
    settings = pd.DataFrame(settings_data, columns=["Setting Key", "Value"])

    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        episode_tracker.to_excel(writer, sheet_name="Episode Tracker", index=False)
        manual_ideas.to_excel(writer, sheet_name="Manual Episode Ideas", index=False)
        prompts_used.to_excel(writer, sheet_name="Prompts Used", index=False)
        settings.to_excel(writer, sheet_name="Settings", index=False)

    print(f"✅ Excel template created at: {file_path}")

# -----------------------------------------
# DATA LOADING FROM FILE OR GOOGLE
# -----------------------------------------
def load_workbook():
    data = try_load_google_sheet()
    if data:
        return data
    if os.path.exists(EXCEL_FILENAME):
        return pd.read_excel(EXCEL_FILENAME, sheet_name=None)
    if os.path.exists(EXCEL_BACKUP):
        return pd.read_excel(EXCEL_BACKUP, sheet_name=None)
    generate_excel_template(EXCEL_FILENAME)
    return pd.read_excel(EXCEL_FILENAME, sheet_name=None)

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
def call_openai_model(prompt, model="gpt-4o", temperature=0.7):
    openai.api_key = OPENAI_API_KEY
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message["content"].strip()
    except Exception as e:
        print(f"❌ OpenAI error: {e}")
        return ""

def generate_voice_audio(text, voice_id, output_path):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.7
        }
    }
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            with open(output_path, 'wb') as f:
                f.write(response.content)
            return output_path
        else:
            print(f"❌ ElevenLabs error: {response.status_code} {response.text}")
    except Exception as e:
        print(f"❌ ElevenLabs API error: {e}")
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

# -----------------------------------------
# MAIN EXECUTION
# -----------------------------------------
if __name__ == '__main__':
    print("🚀 Starting AI Podcast Pipeline")

    # If the workbook doesn't exist, it will be created by load_workbook.
    # We check for its existence first to determine if this is the initial run.
    excel_file_path = EXCEL_FILENAME
    file_existed_before = os.path.exists(excel_file_path)

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    # If the file was just created, exit so the user can populate it first.
    if not file_existed_before:
        print(f"✅ Excel template created at '{excel_file_path}'.")
        print("Please populate the 'Episode Tracker' sheet with your ideas and run the script again.")
        exit(0)

    print("✅ Workbook loaded. Starting episode processing...")
    episode_tracker = dfs.get("Episode Tracker")
    settings = dfs.get("Settings")

    for _, row in episode_tracker.iterrows():
        episode_id = row.get("Episode ID", "unknown")
        print(f"🎙️ Processing Episode: {episode_id}")

        model = get_model_for_step(row, "Research", settings)
        prompt = row.get("Manual Prompt") or "Summarize and expand on today's top 3 AI news stories."
        script = call_openai_model(prompt, model)

        if not script:
            print("⚠ Skipping episode due to script failure.")
            continue

        voice_id = settings.loc[settings['Setting Key'] == 'elevenlabs_voice_id', 'Value'].values[0]
        tts_output = f"{episode_id}_main.mp3"
        final_output = f"{episode_id}_final.mp3"

        if generate_voice_audio(script, voice_id, tts_output):
            intro_path, outro_path = get_intro_outro_paths(row, settings)
            merge_audio(intro_path, tts_output, outro_path, final_output)

        print("✅ Episode complete")
        print("---")
