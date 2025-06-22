import os
import pandas as pd
import gspread
import requests
import openai
from openai import OpenAI
from pydub import AudioSegment
from dotenv import load_dotenv
import time

# Load environment variables from .env file
load_dotenv()

# -----------------------------------------
# CONFIGURATION - Customize as needed
# -----------------------------------------
EXCEL_FILENAME = 'ai_podcast_workflow.xlsx'
EXCEL_BACKUP = 'backup_ai_podcast_workflow.xlsx'
GOOGLE_CREDS_JSON = 'jmio-google-api.json'
GOOGLE_SHEET_NAME = 'AI Podcast Workflow'
GOOGLE_DRIVE_FOLDER_ID = '17XAnga8MC1o23rFhiQ7fcrrqDNhz_-oB'  # Folder to create the sheet in
SHARE_SHEET_WITH_EMAIL = 'ianeoconnell@gmail.com' # <--- CHANGE THIS TO YOUR EMAIL

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', 'your-openai-key')
ELEVENLABS_API_KEY = os.getenv('ELEVENLABS_API_KEY', 'your-elevenlabs-key')

# Instantiate the OpenAI client once using the API key from environment variables
client = OpenAI(api_key=OPENAI_API_KEY)

# -----------------------------------------
# GOOGLE SHEET SUPPORT
# -----------------------------------------
def create_and_setup_google_sheet(gc, sheet_name, folder_id, user_email):
    """Creates and populates a new Google Sheet with the required structure."""
    print(f"✨ Creating new Google Sheet '{sheet_name}'...")
    spreadsheet = gc.create(sheet_name, folder_id=folder_id)
    spreadsheet.share(user_email, perm_type='user', role='writer')

    template_dfs = get_template_dataframes()
    # Define the order of the tabs
    sheet_order = ["Episode Tracker", "Instructions", "Prompts", "Prompts Used", "Settings"]

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
            ws = spreadsheet.add_worksheet(title=title, rows=100, cols=20)
            ws.update([df.columns.values.tolist()] + df.values.tolist())
            # Auto-wrap the text in description columns for readability
            if title in ["Instructions", "Prompts"]:
                ws.format('C:C', {'wrapStrategy': 'WRAP'})
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
            # --- Check if sheet has the new structure. If not, archive and create new. ---
            ep_tracker_ws = spreadsheet.worksheet("Episode Tracker")
            headers = ep_tracker_ws.row_values(1)
            if "Prompt 1 ID" not in headers:
                print("⚠️ Old sheet structure detected. Archiving and creating a new one.")
                archive_name = f"{GOOGLE_SHEET_NAME} (Archived {int(time.time())})"
                gc.rename(spreadsheet, archive_name)
                print(f"  - Old sheet renamed to '{archive_name}'")
                spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)

        except gspread.exceptions.SpreadsheetNotFound:
            spreadsheet = create_and_setup_google_sheet(gc, GOOGLE_SHEET_NAME, GOOGLE_DRIVE_FOLDER_ID, SHARE_SHEET_WITH_EMAIL)

        return {ws.title: pd.DataFrame(ws.get_all_records()) for ws in spreadsheet.worksheets()}
    except Exception as e:
        print(f"⚠ Google Sheets not accessible: {e}")
        return None

# -----------------------------------------
# EXCEL FALLBACK STRUCTURE
# -----------------------------------------
def get_template_dataframes():
    """Returns a dictionary of DataFrames for the template structure."""
    episode_tracker = pd.DataFrame(columns=[
        "Episode ID", "Topic", "Status", "Final Audio Path",
        "Prompt 1 ID", "Response 1",
        "Prompt 2 ID", "Response 2",
        "Prompt 3 ID", "Response 3"
    ])
    prompts_used = pd.DataFrame(columns=[
        "Prompt Step", "Model Used", "Prompt Text", "Tokens Used", "Cost (USD)", "Timestamp"
    ])
    instructions_data = [
        [
            "Workflow", "1. Define Prompts", "In the 'Prompts' tab, create reusable prompts. Give each a unique ID."
        ],
        [
            "", "2. Design an Episode", "In 'Episode Tracker', add a row for a new episode. Give it an ID and a 'Topic'."
        ],
        [
            "", "3. Create a Prompt Chain", "Fill in the 'Prompt 1 ID', 'Prompt 2 ID', etc. to define the sequence of steps for your episode."
        ],
        [
            "", "4. Run the Script", "The script will execute the steps in order. It uses the 'Topic' as input for the first prompt, and the response from step N as input for step N+1."
        ],
        [
            "Audio Generation", "How it Works", "If the title of the LAST prompt in your chain includes the word 'script', the script will automatically use that response to generate the final audio file."
        ]
    ]
    instructions = pd.DataFrame(instructions_data, columns=["Category", "Step", "Description"])

    prompts_data = [
        [
            1, "Daily AI News Summary",
            ("Please provide a comprehensive overview of the most important news in AI that occurred in the last 24-48 hours. "
             "The topic for today is: ")
        ],
        [
            2, "Generate Podcast Script from Summary",
            ("Based on the news summary below, please write an engaging and informative podcast script. The script should be conversational. "
             "Start with a hook, introduce the topics, discuss each one in detail, and end with a concluding thought. Here is the summary:\n\n")
        ],
        [
            3, "Generate 5 Podcast Titles from Script",
            "Based on the following podcast script, generate 5 compelling and SEO-friendly titles for the episode. Here is the script:\n\n"
        ]
    ]
    prompts = pd.DataFrame(prompts_data, columns=["Prompt ID", "Prompt Title", "Prompt Description"])

    settings_data = [
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

    return {
        "Episode Tracker": episode_tracker,
        "Instructions": instructions,
        "Prompts": prompts,
        "Prompts Used": prompts_used,
        "Settings": settings
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
    # Google Sheets is now the primary, with automated creation
    data = try_load_google_sheet()
    if data:
        return data

    print("Falling back to local Excel file.")
    if os.path.exists(EXCEL_FILENAME):
        return pd.read_excel(EXCEL_FILENAME, sheet_name=None)
    if os.path.exists(EXCEL_BACKUP):
        return pd.read_excel(EXCEL_BACKUP, sheet_name=None)

    # Generate Excel only if Google Sheets fails and no local file exists
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
    """Calls the OpenAI Chat Completion API with the new v1.x syntax."""
    if not client.api_key:
        print("❌ OpenAI API key is not configured. Please check your .env file.")
        return ""
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature
        )
        return response.choices[0].message.content.strip()
    except openai.APIConnectionError as e:
        print(f"❌ OpenAI API Connection Error: {e.__cause__}")
        return ""
    except openai.RateLimitError as e:
        print(f"❌ OpenAI Rate Limit Exceeded: {e.status_code} {e.response}")
        return ""
    except openai.APIStatusError as e:
        print(f"❌ OpenAI API Status Error: {e.status_code} {e.response}")
        return ""
    except Exception as e:
        print(f"❌ An unexpected OpenAI error occurred: {e}")
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

    dfs = load_workbook()
    if not dfs:
        print("❌ Failed to load or create workbook. Please check file permissions or configuration.")
        exit(1)

    print("✅ Workbook loaded. Starting episode processing...")
    # It's safer to get fresh copies of the sheets each time we might modify them
    gc = connect_to_google_sheet()
    spreadsheet = gc.open(GOOGLE_SHEET_NAME)
    episode_tracker_ws = spreadsheet.worksheet("Episode Tracker")
    episode_tracker_df = pd.DataFrame(episode_tracker_ws.get_all_records())
    prompts_df = pd.DataFrame(spreadsheet.worksheet("Prompts").get_all_records())
    settings = pd.DataFrame(spreadsheet.worksheet("Settings").get_all_records())

    for index, row in episode_tracker_df.iterrows():
        episode_id = row.get("Episode ID")
        if not episode_id:
            continue

        print(f"🎙️ Processing Episode: {episode_id}")
        last_response = row.get("Topic", "") # Start the chain with the topic
        last_successful_step = 0

        # Loop through prompt steps (1, 2, 3...)
        for i in range(1, 10): # Process up to 9 steps
            prompt_id_col = f"Prompt {i} ID"
            response_col = f"Response {i}"

            if prompt_id_col not in row or response_col not in row:
                # We've reached the end of the defined prompt columns
                if last_successful_step > 0:
                    print(f"  ✅ Chain complete for Episode {episode_id}.")
                break

            prompt_id = str(row.get(prompt_id_col, "")).strip()
            response = str(row.get(response_col, "")).strip()

            # If this step is already done, move to the next
            if prompt_id and response:
                last_response = response # Keep track of the last valid response
                last_successful_step = i
                continue

            # If there's a prompt but no response, execute it
            if prompt_id and not response:
                print(f"  - Executing Step {i} with Prompt ID '{prompt_id}'...")
                prompt_row = prompts_df[prompts_df['Prompt ID'].astype(str) == prompt_id]
                if prompt_row.empty:
                    print(f"    - ⚠ Error: Prompt ID '{prompt_id}' not found in 'Prompts' tab.")
                    break # Stop processing this episode chain

                prompt_template = prompt_row.iloc[0]['Prompt Description']
                full_prompt = f"{prompt_template}{last_response}"

                # Call the model
                model = get_model_for_step(row, "Research", settings)
                model_response = call_openai_model(full_prompt, model)

                if model_response:
                    # Save response to sheet
                    # Adding 2 because sheet is 1-indexed and has a header row
                    episode_tracker_ws.update_cell(index + 2, episode_tracker_df.columns.get_loc(response_col) + 1, model_response)
                    print(f"    - ✅ Success. Response saved to '{response_col}'.")
                    last_response = model_response
                    last_successful_step = i

                    # CHECK FOR AUDIO GENERATION
                    # If this was the last prompt in the chain, check if it was a script
                    next_prompt_col = f"Prompt {i+1} ID"
                    is_last_prompt = str(row.get(next_prompt_col, "")).strip() == ""
                    prompt_title = prompt_row.iloc[0]['Prompt Title'].lower()

                    if is_last_prompt and "script" in prompt_title:
                        print("  - 🎤 'script' prompt detected as final step. Generating audio...")
                        intro_path, outro_path = get_intro_outro_paths(row, settings)
                        voice_id = settings.loc[settings['Setting Key'] == 'elevenlabs_voice_id', 'Value'].values[0]
                        tts_output = f"{episode_id}_main.mp3"
                        final_output = f"{episode_id}_final.mp3"

                        if generate_voice_audio(last_response, voice_id, tts_output):
                             merge_audio(intro_path, tts_output, outro_path, final_output)
                             episode_tracker_ws.update_cell(index + 2, episode_tracker_df.columns.get_loc("Final Audio Path") + 1, final_output)
                             episode_tracker_ws.update_cell(index + 2, episode_tracker_df.columns.get_loc("Status") + 1, "Complete")
                else:
                    print(f"    - ❌ Failure. Halting chain for Episode {episode_id}.")
                    episode_tracker_ws.update_cell(index + 2, episode_tracker_df.columns.get_loc("Status") + 1, f"Error on Step {i}")
                    break # Stop processing this episode chain
            
            # If there's no prompt ID, the chain is done
            elif not prompt_id:
                if last_successful_step > 0:
                     print(f"  ✅ Chain complete for Episode {episode_id}.")
                break

        print("---")
