import gspread
from oauth2client.service_account import ServiceAccountCredentials

from config import load_config


config = load_config()

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

creds = ServiceAccountCredentials.from_json_keyfile_name(
    'random_coffee_bot/credentials.json', scopes=SCOPES
)
gc = gspread.authorize(creds)

SHEET_ID = config.g_sheet.sheet_id
sh = gc.open_by_key(SHEET_ID)

users_sheet = sh.worksheet('users')
pairs_sheet = sh.worksheet('pairs')
