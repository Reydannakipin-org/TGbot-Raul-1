# import random
# import gspread
# from oauth2client.service_account import ServiceAccountCredentials
#
# # Настройка доступа
# scope = [
#     "https://spreadsheets.google.com/feeds",
#     "https://www.googleapis.com/auth/spreadsheets",
#     "https://www.googleapis.com/auth/drive.file",
#     "https://www.googleapis.com/auth/drive"
# ]
#
# def connect_to_sheets():
#     creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
#     client = gspread.authorize(creds)
#     sheet = client.open("test_for_bot").sheet1
#     sheet_pair = client.open("pair").sheet1
#     return sheet, sheet_pair
#
# def generate_pairs(sheet, sheet_pair):
#     # Список пользователей со 2 строки
#     users = [u.strip() for u in sheet.col_values(1)[1:] if u.strip()]
#     random.shuffle(users)
#
#     # Читаем существующие пары из таблицы pair
#     existing_pairs_raw = sheet_pair.col_values(1)
#     user_history = {user: set() for user in users}
#
#     for pair in existing_pairs_raw:
#         if "-" in pair:
#             parts = [p.strip() for p in pair.split("-")]
#             if len(parts) == 2:
#                 name1, name2 = sorted(parts)
#                 user_history.setdefault(name1, set()).add(name2)
#                 user_history.setdefault(name2, set()).add(name1)
#
#     # Генерация новых уникальных пар
#     new_pairs = []
#     used_users = set()
#
#     for user in users:
#         if user in used_users:
#             continue
#
#         possible_partners = [u for u in users if u != user and u not in user_history[user] and u not in used_users]
#
#         if possible_partners:
#             partner = possible_partners[0]  # можно сделать random.choice(possible_partners)
#             pair_str = f"{user} - {partner}"
#             new_pairs.append([pair_str])
#             user_history[user].add(partner)
#             user_history[partner].add(user)
#             used_users.add(user)
#             used_users.add(partner)
#         else:
#             print(f"{user} не удалось найти уникального партнёра.")
#
#     return new_pairs
#
# def save_new_pairs(sheet_pair, new_pairs):
#     def find_first_empty_row(sheet):
#         values = sheet.col_values(1)
#         for i, val in enumerate(values, start=1):
#             if val.strip() == "":
#                 return i
#         return len(values) + 1
#
#     if new_pairs:
#         start_row = find_first_empty_row(sheet_pair)
#         range_start = f"A{start_row}"
#         sheet_pair.update(values=new_pairs, range_name=range_start)
#         print(f"Добавлено {len(new_pairs)} новых уникальных пар.")
#     else:
#         print("Не удалось создать новых уникальных пар.")