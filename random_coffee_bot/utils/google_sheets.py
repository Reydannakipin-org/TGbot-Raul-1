import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Области доступа
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Авторизация по JSON-ключу
creds = ServiceAccountCredentials.from_json_keyfile_name(
    'random_coffee_bot/credentials.json', scopes=SCOPES
)
gc = gspread.authorize(creds)

# Открываем таблицу по ключу (ID в URL)
SPREADSHEET_ID = "1IhMyK45CFC4XTaSfZ-b2hXwdNSZgxzzquLTDODLD9KU"
sh = gc.open_by_key(SPREADSHEET_ID)

# Выбираем лист
users_sheet = sh.worksheet("users")
pais_sheet = sh.worksheet("pairs")
