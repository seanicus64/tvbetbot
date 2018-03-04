#!/usr/bin/env python3
import praw
import dateparser 
import sqlite3 as sql
import random
con = sql.connect("example.sql")
cur = con.cursor()

reddit = praw.Reddit("bot1")
subreddit = reddit.subreddit("sje46")
all_shows = ["Mr_Robot", "Star_Wars", "GOT", "BCS", "US_Politics", "reddit_drama"]
def check_player(author):
    name = author.name
    cur.execute("SELECT * FROM bank WHERE player = ? ", (name,))
    results = cur.fetchall()
    if not results:
        cur.execute("INSERT INTO bank VALUES (?, ?, ?)", (name , 1000, 0))
        con.commit()


def handle_offer(comment):
    offer, cat_id, end_date, reveal_date, options = parse_offer(comment)
    bet_id = SQL_add_offer(offer, cat_id, comment.author.name, int(comment.created_utc), \
        end_date, reveal_date, comment.id, options)
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for e, o in enumerate(options):
        SQL_add_option(o[0], bet_id, o[1], labels[e])
    text = reply_offer_bet(bet_id)
    comment.reply(text)
def parse_offer(comment):
    # first line must be $add [label] [question]
    check_player(comment.author)
    text = comment.body
    lines = text.split("\n")
    lines = [x.strip() for x in lines]
    first_line = lines[0].split()
    offer = " ".join(first_line[2:])

    options = list(filter(lambda l: l.startswith("* "), lines[1:]))
    confirmed = []
    for o in options:
        split = o.split()
        odds = split[1]
        try:
            odds = float(odds)
        except ValueError:
            return
        if odds < 1:
            return
        option = " ".join(split[2:])
        confirmed.append((option, odds))
    for line in lines:
        if line.lower().startswith("end:"):
            end_date = dateparser.parse(line[4:])
        if line.lower().startswith("reveal:"):
            reveal_date = dateparser.parse(line[7:])
        if line.lower().startswith("category:"):
            line = line.lower()
            category = line.lstrip("category:").strip()
    cat_id = SQL_get_cat_id(category)
    response = (offer, cat_id, end_date.timestamp(), reveal_date.timestamp(), confirmed)
    return response
def SQL_get_cat_id(category):
    cur.execute("""
        SELECT 1 FROM categories 
        WHERE lower(short) = ?
        """, (category,))
    response = cur.fetchone()
    print(category)
    print(response)
    if not response: raise Exception
    return response[0]
def SQL_add_offer(bet, cat_id, author, created, end, reveal, source, options):
    cur.execute("""
        SELECT 1 FROM bets 
        WHERE source = ?
        """, (source,))
    response = cur.fetchone()
    if response:
        return
    cur.execute("""
        INSERT INTO bets 
            (bet, creator, created, expires, 
            reveal, source, ended, cat_id) 
        VALUES
            (?, ?, ?, ?, ?, ?, ?, ?)
    """, (bet, author, created, end, reveal, source, 0, cat_id))
    cur.execute("""SELECT bet_id FROM bets WHERE source=?""", \
            (source,))
    bet_id = cur.fetchone()[0]
    con.commit()
    return bet_id
def SQL_add_option(option_text, bet_id, multiplier, label):
    cur.execute("""
        INSERT INTO options 
            (option, bet_id, multiplier, label) 
        VALUES
            (?, ?, ?, ?)
        """, (option_text, bet_id, multiplier, label))
    con.commit()
def reply_offer_bet(bet_id):
    bet, creator, created, expires, reveal, ended, cat_id = \
        SQL_bet_info(bet_id)[0]
    options = SQL_option_info(bet_id)
    text = ""
    text += "--------  \n\n"
    text += "[{}:{}] **Bet**: {}  \n\n\n".format(cat_id, bet_id, bet)
    text += "|Label|Option|Odds|Probability|\n"
    text += "|----:|:-----|:--:|:---------:|\n"
    for o in SQL_option_info(bet_id):
        _, option, _, multiplier, label = o
        probability = 1/multiplier
        text += "|**{}**|{}|{}|{:.3f}|\n".format(label, option, multiplier, probability)
    return text
def handle_bet(comment):
    option_id, amount = parse_bet(comment)
    name = comment.author.name
    source = comment.id
    check_player(comment.author)
    if not check_if_enough_money(name, amount):
        return
    SQL_take_bet(name, option_id, amount, source)

def parse_bet(comment):
    lines = comment.body.split("\n")
    first_line = lines[0].split()
    _, bet_id, label, amount = first_line[:4]
    amount = int(amount)
    name = comment.author.name
    option_id = find_option(bet_id, label)
    if not option_id: 
        return
    option_id = option_id[0]
    return option_id, amount
def SQL_find_option(bet_id, label):
    cur.execute("""
        SELECT option_id FROM options
        WHERE bet_id = ? AND label = ?
        """, (bet_id, label))
    result = cur.fetchone()
    return result
def SQL_take_bet(name, option_id, amount, source):
    cur.execute("""
        INSERT INTO amounts
            (option_id, bettor, amount, source)
            VALUES (?, ?, ?, ?)
            """, (option_id, name, amount, source))
    con.commit()
    
def check_if_enough_money(name, amount):
    cur.execute("""
        SELECT balance FROM bank
        WHERE player = ?
        """, (name,))
    result = cur.fetchone()
    result = int(result[0])
    if result < amount:
        return False
    return True
def SQL_bet_info(bet_id):
    cur.execute("""
        SELECT bet, creator, created, expires, reveal, ended, cat_id
        FROM bets WHERE bet_id = ?
        """, (bet_id,))
    result = cur.fetchall()

    return result
def SQL_option_info(bet_id):
    cur.execute("""
        SELECT * FROM options WHERE bet_id = ?
        """, (bet_id,))
    result = cur.fetchall()
    return result
def handle_call(comment):
    pass
def parse_call(comment):
    # !call_bet 123 A
    pass
    
submission = reddit.submission(id="80a8c9")
submission.comment_sort = "old"
for comment in submission.comments.list():
    text = comment.body.split()
    if len(text) >= 2:
        if text[0] == "!offer_bet":
            try: handle_offer(comment)
            except: pass
        if text[0] == "!bet":
            pass
        if text[0] == "!call_bet":
            handle_call(comment)

            
