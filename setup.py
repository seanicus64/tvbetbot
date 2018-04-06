#!/usr/bin/env python3
import sqlite3 as SQL
import os
def recreate_database():
    try:
        os.remove("bets.sql")
    except FileNotFoundError:
        pass
    con = SQL.connect("bets.sql")
    cur = con.cursor()
    cur.execute("""
        CREATE TABLE "bank" 
        (player VARCHAR(20) PRIMARY KEY, 
        balance int, in_play int)
        """)
    cur.execute("""
        CREATE TABLE "categories" 
        (cat_id VARCHAR(5) UNIQUE PRIMARY KEY, 
        description VARCHAR(255), hub VARCHAR[20] DEFAULT NULL);
        """)
    cur.execute("""
        CREATE TABLE "judges" 
        (user VARCHAR(20), cat_id VARCHAR(20), 
        FOREIGN KEY(cat_id) REFERENCES categories(cat_id));
        """)
    cur.execute("""
        CREATE TABLE "bets" 
        (bet_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        bet VARCHAR(255), creator VARCHAR(20), 
        created int, expires int, reveal int, 
        source VARCHAR(20), ended int, cat_id VARCHAR(5), 
        closed int DEFAULT '0', revealed int DEFAULT '0', 
        FOREIGN KEY (creator) REFERENCES bank(player), 
        FOREIGN KEY (cat_id) REFERENCES categories(cat_id));
        """)
    cur.execute("""
        CREATE TABLE "options" 
        (option_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        option VARCHAR(255), bet_id int, multiplier real, 
        label VARCHAR(1), FOREIGN KEY(bet_id) 
        REFERENCES bets(bet_id));
        """)
    cur.execute("""
        CREATE TABLE "amounts" 
        (amount_id INTEGER PRIMARY KEY AUTOINCREMENT, 
        option_id int, bettor VARCHAR(20), amount int, 
        source VARCHAR(20), FOREIGN KEY (option_id) 
        REFERENCES options(option_id), 
        FOREIGN KEY (bettor) REFERENCES bank(player));
        """)
def add_cat(cat_id, desc):
    cur.execute("""
        INSERT INTO categories VALUES (?, ?)
        """, (cat_id, desc))
def add_judge(name, cat_id):
    cur.execute("""
        INSERT INTO judges VALUES (?, ?)
        """, (name, cat_id))
recreate_database()

