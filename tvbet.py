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
    
#    cur.execute("SELECT * FROM 'bank'")
    cur.execute("SELECT * FROM bank WHERE player = ? ", (name,))
    results = cur.fetchall()
    if not results:
        cur.execute("INSERT INTO bank VALUES (?, ?, ?)", (name , 1000, 0))
        con.commit()



def parse_offer(comment):
    # first line must be $add [label] [question]
    # two things:
    #   check/add player to the game (bank)
    #   check if bet already added
    #TODO: parsing options is way too strict!  Careful
    # with whitespace, etc
    print("parsing offer")
    check_player(comment.author)
    response = ""
    text = comment.body
    lines = text.split("\n")
    lines = [x.strip() for x in lines]
    first_line = lines[0].split()
    label = first_line[1]
    question = " ".join(first_line[2:])

    options = list(filter(lambda l: l.startswith("* "), lines[1:]))
    print("options")
    confirmed = []
    for o in options:
        split = o.split()
        odds = split[1]
        try:
            odds = float(odds)
        except ValueError:
            print("problem with floating({})".format(odds))
            return
        if odds < 1:
            return

        option = " ".join(split[2:])
        confirmed.append((option, odds))
    print(confirmed)
#        put_in, _, winnings = odds.partition("/")
#        if len(put_in.split()) == 1 and put_in.isdigit() and \
#            len(winnings.split()) == 1 and winnings.isdigit():
#                multiplier = int(winnings) / int(put_in)
#                confirmed.append(
#        left, _, right = o.partition(" - ")
##        left = left.strip("* ")
 #3       put_in, _, winnings = right.partition("/")
#        if len(put_in.split()) == 1 and put_in.isdigit() and \
#            len(winnings.split()) == 1 and winnings.isdigit():
#                multiplier = int(winnings) / int(put_in) 
#                confirmed.append((left, multiplier))
    for line in lines:
        if line.lower().startswith("end:"):
            end_date = dateparser.parse(line[4:])
        if line.lower().startswith("reveal:"):
            reveal_date = dateparser.parse(line[7:])
    print("CONFIRMED")
    print(confirmed)
    bet_id = add_bet(question, comment.author.name, \
        int(comment.created_utc), int(end_date.timestamp()), \
        int(reveal_date.timestamp()), comment.id, confirmed)
    print("BET ID IS")
    print(bet_id)
    if not bet_id:
        return
    text = reply_new_bet(bet_id)
    comment.reply(text)
def add_option(option_text, bet_id, multiplier, label):
    cur.execute("""
    INSERT INTO options 
        (option, bet_id, multiplier, label) 
    VALUES
        (?, ?, ?, ?)
    """, (option_text, bet_id, multiplier, label))
    con.commit()
def add_bet(bet, author, created, end, reveal, source, options):
    cur.execute("""
    SELECT 1 FROM bets 
    WHERE source = ?""", (source,))
    response = cur.fetchone()
    if response:
        return
    cur.execute("""
    INSERT INTO bets 
        (bet, creator, created, expires, 
        reveal, source, ended) 
    VALUES
        (?, ?, ?, ?, ?, ?, ?)
    """, (bet, author, created, end, reveal, source, 0))
    cur.execute("""SELECT bet_id FROM bets WHERE source=?""", \
            (source,))
    bet_id = cur.fetchone()[0]
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for e, o in enumerate(options):
        add_option(o[0], bet_id, o[1], labels[e])
    con.commit()
    return bet_id
def find_option_taken(bet_id, label):
    cur.execute("""
    SELECT option_id FROM options
    WHERE bet_id = ? AND label = ?""", (bet_id, label))
    result = cur.fetchone()
    return result
def take_bet(name, option_id, amount, source):
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
def parse_take_bet(comment):
    source = comment.id
    lines = comment.body.split("\n")
    first_line = lines[0].split()
    _, bet_id, label, amount = first_line[:4]
    amount = int(amount)
    name = comment.author.name
    check_player(comment.author)
    option_id = find_option_taken(bet_id, label)
    if not option_id: 
        print("invalid option")
        return
    option_id = option_id[0]
    if not check_if_enough_money(name, amount):
        print("not enough money")
        return
    take_bet(name, option_id, amount, source)
#    SQL_bet_info(bet_id)
def SQL_bet_info(bet_id):
    print(bet_id)
    cur.execute("""
    SELECT bet, creator, created, expires, reveal, ended
    FROM bets WHERE bet_id = ?
    """, (bet_id,))
    result = cur.fetchall()

    print(result)
    return result
def SQL_option_info(bet_id):
    cur.execute("""
    SELECT * FROM options WHERE bet_id = ?
    """, (bet_id,))
    result = cur.fetchall()
    return result
def reply_new_bet(bet_id):
    import fractions
    print("++++++++++++")
    print(bet_id)
    bet, creator, created, expires, reveal, ended = \
        SQL_bet_info(bet_id)[0]
    options = SQL_option_info(bet_id)
    text = ""
    text += "--------  \n\n"
    text += "[{}] **Bet**: {}  \n\n\n".format(bet_id, bet)
    text += "|Label|Option|Odds|Multiplier|\n"
    text += "|:----|:-----|:--:|:--------:|\n"
    for o in SQL_option_info(bet_id):
        _, option, _, multiplier, label = o
        fraction = str(fractions.Fraction(multiplier).limit_denominator(1000))
        if "/" not in fraction:
            fraction += "/1"
        text += "|**{}**|{}|{}|{}|\n".format(label, option, fraction, multiplier)
    
    print(text)
    return text


    
    #    lines.append(str(
     

    


submission = reddit.submission(id="80a8c9")
submission.comment_sort = "old"
for comment in submission.comments.list():
    text = comment.body.split()
    replied_already = False
    for c in comment.replies:
        if c.author == reddit.redditor("tvbetbot"):
            replied_already = True
    #if replied_already:
    #    continue
    if len(text) >= 2:
        if text[0] == "!add":
#            try:
                parse_offer(comment)
#                parse_take_bet(comment)
#            except:
#                print("bad syntax")
#        if text[0] == "bet" and text[1].isdigit():
#            body = """
#{} bet {}!\n-----
#current amount: {}""".format(comment.author, text[1], 54000)
#            comment.reply(body)
#        if text[0] == "!add":
#            parse_bet(comment)
