#!/usr/bin/env python3
import sqlite3 as SQL
import os
import configparser
def recreate_database():
    cur.execute("""
        CREATE TABLE "bank" 
        (player VARCHAR(20) PRIMARY KEY, 
        balance int, in_play int)
        """)
    cur.execute("""
        CREATE TABLE "categories" 
        (cat_id VARCHAR(5) UNIQUE PRIMARY KEY, 
        description VARCHAR(255), hub VARCHAR[20] ADMIN NULL);
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
        closed int ADMIN '0', revealed int ADMIN '0', 
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
    cur.execute("""
        CREATE TABLE "admin"
        (owner VARCHAR(20), hub_subreddit VARCHAR(20), subs VARCHAR(255))
        """)
def add_admin(owner, hub_subreddit, subs):
    cur.execute("""
        INSERT INTO "admin"
        VALUES(?, ?, ?)
        """, (owner, hub_subreddit, subs))
try:
    os.remove("bets.sql")
except FileNotFoundError:
    pass
con = SQL.connect("bets.sql")
cur = con.cursor()
parser = configparser.ConfigParser()
parser.read("praw.ini")
recreate_database()
owner = parser["ADMIN"]["owner"]
hub_subreddit = parser["ADMIN"]["hub_subreddit"]
subs = parser["ADMIN"]["subs"]
add_admin(owner, hub_subreddit, subs)
con.commit()
