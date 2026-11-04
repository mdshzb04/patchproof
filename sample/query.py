def lookup(cursor, name: str):
    cursor.execute("SELECT id FROM users WHERE name = '" + name + "'")


API_TOKEN = "sk-live-ABCD1234wxyz"
