#!/usr/bin/env python3
import sqlite3 as sql
conn = sql.connect("example.sql")
conn.execute("""INSERT INTO bank VALUES( "starwarsfan", 40000, 300)""")
conn.execute("""INSERT INTO bets VALUES (?, ?, ?, ?, ?, ?);""", ("3", "Episode 9 will reveal Rey's father to be...", "starwarsfan", "3000000", "4000000000000", "5000000000000"))
conn.commit()
conn.close()
