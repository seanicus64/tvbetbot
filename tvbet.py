#!/usr/bin/env python3
import praw
import dateparser 
import sqlite3 as sql
import random
import signal
import datetime
class Error(Exception):
    pass
class OfferSyntaxError(Error):
    def __init__(self, value):
        self.value = value

class OfferLegalityError(Error):
    def __init__(self, value):
        self.value = value
con = sql.connect("example.sql")
cur = con.cursor()

reddit = praw.Reddit("bot1")
def human_date(timestamp):
    return datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
def check_player(author):
    name = author.name
    cur.execute("SELECT * FROM bank WHERE player = ? ", (name,))
    results = cur.fetchall()
    if not results:
        cur.execute("INSERT INTO bank VALUES (?, ?, ?)", (name , 1000, 0))
        con.commit()


def handle_offer(comment):
    """Handles a comment offering a bet.
    !offer_bet [bet]

    * [mult] [option]
    * [mult] [option]

    Ends: [Date]  
    Reveal: [Date]  
    Category: [cat_id]"""
    
    check_player(comment.author)
    offer, category, end_date, reveal_date, options = parse_offer(comment)
    cat_id, end_date, reveal_date = offer_fixer(end_date, reveal_date, category)
    
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    bet_id = SQL_add_offer(offer, cat_id, comment.author.name, int(comment.created_utc), \
        end_date, reveal_date, source, options)
    
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for e, o in enumerate(options):
        SQL_add_option(o[0], bet_id, o[1], labels[e])
    
    text = reply_offer_bet(bet_id)
    #comment.reply(text) #TODO
    print("REPLY TO COMMENT: {}".format(text))

def handle_bet(comment):
    bet_id, option, amount = parse_bet(comment)
    option_id = SQL_find_option(bet_id, option)
    if not option_id: 
        raise Error("Option does not exist.")
    option_id = option_id[0]

    name = comment.author.name
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    check_player(comment.author)
    if not check_if_enough_money(name, amount):
        raise Error("You don't have enough money.")
    SQL_take_bet(name, option_id, amount, source)
    SQL_change_bank(name, -amount)
    text = reply_to_bet(name, amount, option_id, bet_id, option)
    

def reply_to_bet(name, amount, option_id, bet_id, option_label):
    multiplier = SQL_get_specific_option_info(option_id)[3]
    new = SQL_get_balance(name)
    old = new + amount
    potential_winnings = int(amount * multiplier)
    follow = "TODO"
    text = """
    *{}* bet {} on {}.{}  
    Old balance: {}  
    New balance: {}  
    Potential winnings: +{}  
    Follow this bet here: {}""".format(name, amount, bet_id, option_label,\
            old, new, potential_winnings, follow)
    print(text)
    return text
def handle_call(comment):
    bet_id, label = parse_call(comment)
    bet_info = SQL_bet_info(bet_id)
    if not bet_info: 
        raise Error("You called a bet that doesn't exist.")
    creator = bet_info[1]
    cat_id = bet_info[6]
    option_id = SQL_find_option(bet_id, label)
    if not option_id: 
        raise Error("You called an option that doesn't exist.")
    option_id = option_id[0]
    if not comment.author.name in SQL_get_judges(cat_id):
        raise Error("You're not a judge for this category.")

    # Now that everything is legal, we can get to the meat of it.
    amount_owned_by_creator = SQL_get_balance(creator)
    winners = SQL_amounts_winners(option_id)
    multiplier = SQL_get_specific_option_info(option_id)[3]
    all_options = [x[0] for x in SQL_option_info(bet_id)]
    pot = 0
    for o in all_options:
        pot += SQL_derive_pot_from_bets(o)
    pot_before = pot
    profit = 0
    for winner in winners:
        name, amount = winner[2:4]
        winnings = int(amount * multiplier)
        SQL_change_bank(name, winnings)
        pot -= winnings
        profit += (winnings / 10)
    creator_new_worth = amount_owned_by_creator + profit + pot
    SQL_change_bank(creator, profit + pot)

def parse_offer(comment):
    """parses an !offer_bet command, returning the relevant values"""
    # first line must be $add [label] [question]
    text = comment.body
    lines = text.split("\n")
    lines = [x.strip() for x in lines]
    first_line = lines[0].split()
    offer = " ".join(first_line[1:])
    if not offer: raise OfferSyntaxError("No offer made in first line")
    try:
        assert len(offer) <= 255
    except:
        raise OfferSyntaxError("Offer must be less than 255 characters long.")

    options = list(filter(lambda l: l.startswith("* "), lines[1:]))
    if not options:
        raise OfferSyntaxError("No options given")
    confirmed = []
    for o in options:
        split = o.split()
        if len(split) < 3:
            raise OfferSyntaxError("Option syntax must be * [multiplier > 1] [Option]")
        odds = split[1]
        try:
            odds = float(odds)
        except ValueError:
            raise OfferSyntaxError("Option syntax must be * [multiplier > 1] [Option]")
        if odds <= 1:
            raise OfferSyntaxError("Option syntax must be * [multiplier > 1] [Option]")
        option = " ".join(split[2:])
        try:
            assert len(option) <= 255
        except: raise OfferSyntaxError("Option must be less than 256 characters long.")
        confirmed.append((option, odds))
    end_date = None
    reveal_date = None
    category = None
    for line in lines:
        if line.lower().startswith("end:"):
            end_date = dateparser.parse(line[4:])
        if line.lower().startswith("reveal:"):
            reveal_date = dateparser.parse(line[7:])
        if line.lower().startswith("category:"):
            line = line.lower()
            category = line.lstrip("category:").strip()
    if not end_date:
        raise OfferSyntaxError("Invalid end date")
    if not reveal_date:
        raise OfferSyntaxError("Invalid reveal date.")
    if not category: 
        raise OfferSyntaxError("Must include category tag")
    response = (offer, category, end_date, reveal_date, confirmed)
    return response
    
def offer_fixer(reveal_date, end_date, category):
    now = dateparser.parse("Now")

    if (reveal_date - now).total_seconds() < 0:
        raise OfferLegalityError("Reveal date set in past.")
    if (end_date - now).total_seconds() < 0:
        raise OfferLegalityError("End date set in past.")
    if (reveal_date - end_date).total_seconds() > 0:
        raise OfferLegalityError("End date occurs after reveal date.")
    
    cat_id = SQL_get_cat_id(category)
    cat_id = category.upper()
    response = (cat_id, end_date.timestamp(), reveal_date.timestamp())
    return response

def parse_bet(comment):
    print(comment.body)
    lines = comment.body.split("\n")
    first_line = lines[0].split()
    if len(first_line) != 4:
        
        raise Error("Command requires exactly four arguments")
    
    print(len(first_line))
    _, bet_id, label, amount = first_line[:4]
    if label.upper() not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        raise Error("label must be an ascii letter")
    if not bet_id.isdigit():
        raise Error("bet_id must be an integer.")
    if not amount.isdigit() or int(amount) < 1:
        raise Error("amount must be an integer greater than zero.")

    amount = int(amount)
    return bet_id, label, amount

def parse_call(comment):
    # !call_bet 123 A
    split = comment.body.split()
    bet_id = split[1]
    label = split[2].upper()
    return bet_id, label

def SQL_get_cat_id(category):
    cur.execute("""
        SELECT 1 FROM categories 
        WHERE upper(cat_id) = ?
        """, (category.upper(),))

    response = cur.fetchone()
    print("response: {}".format(response))
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
    print(bet_id)
    bet, creator, created, expires, reveal, ended, cat_id = \
        SQL_bet_info(bet_id)
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
    

def SQL_find_option(bet_id, label):
    print(bet_id, label)
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
    result = cur.fetchone()

    return result

def SQL_option_info(bet_id):
    cur.execute("""
        SELECT * FROM options WHERE bet_id = ?
        """, (bet_id,))
    result = cur.fetchall()
    return result
def SQL_get_specific_option_info(option_id):
    cur.execute("""
        SELECT * FROM options WHERE option_id = ?
        """, (option_id,))
    result = cur.fetchone()
    return result
def SQL_amounts_winners(option_id):
    cur.execute("""
        SELECT * FROM amounts WHERE option_id = ?
        """, (option_id,))
    result = cur.fetchall()
    return result
def SQL_get_judges(cat_id):
    cur.execute("""
        SELECT user FROM judges WHERE cat_id = ?
        """, (cat_id,))
    print(cat_id)
    result = cur.fetchall()
    result = [x[0] for x in result]

    return result
def SQL_get_balance(creator):
    cur.execute("""
        SELECT balance FROM bank
        WHERE player = ?
        """, (creator,))
    response = cur.fetchone()[0]
    return response
def SQL_change_bank(name, winnings):
    cur.execute("""
        UPDATE bank 
        SET balance = balance + ?
        WHERE player = ?
        """, (winnings, name))
    con.commit()
    pass
def SQL_derive_pot_from_bets(opt_id):
    cur.execute("""
        SELECT amount FROM amounts
        WHERE option_id = ?
        """, (opt_id,))
    result = cur.fetchall()
    if not result: return 0
    result = sum([x[0] for x in result])
    return result
def nuke_thread(submission):

    submission.comment_sort = "old"
    for comment in submission.comments.list():
        if not comment.removed:
            comment.mod.remove()
def nuke_database():
    cur.execute("DELETE FROM bets")
    cur.execute("DELETE FROM bank")
    cur.execute("DELETE FROM amounts")
    cur.execute("DELETE FROM options")
    cur.execute("DELETE FROM categories")
    cur.execute("DELETE FROM judges")
    con.commit()

def nuke_it_all(submission):
        
    nuke_thread(submission)
    nuke_database()
def rebuild_database():
    cur.execute("INSERT INTO categories VALUES ('TEST', 'A test category')")
    cur.execute("INSERT INTO judges VALUES ('testjudge', 'TEST')")
    con.commit()

def rebuild(submission):
    rebuild_database()
    offer_comment_2 = submission.reply("""!offer_bet The capital of Canada is

* 1.25 Ottawa 1
* 5.0 Toronto

Category: TEST  
END: Tomorrow
Reveal: 1/1/2024""")
    try:
        parse_offer(offer_comment_2)
    except Error as e:
        print(e)
    return
    cur.execute("""SELECT MAX(bet_id) FROM bets""")
    bet_id2 = cur.fetchone()[0]
    
    offer_comment_2.reply("!bet {} {} {}  \n On behalf of testuser1".format(bet_id2, "A", 67))


    offer_comment = submission.reply("""!offer_bet The capital of Colombia is  

* 4.0 Bogota  
* 2.0 Medellin  
* 1.5 Cartegena  
* 1.24 Santa Maria  
* 1.04 Bucamaranga  

Category: TEST  
End: 1/1/2020  
Reveal: 1/1/2024  
        """)

    print(offer_comment)
    parse_comment(offer_comment)
    cur.execute("""SELECT MAX(bet_id) FROM bets""")
    bet_id = cur.fetchone()[0]
    for i in range(0):
        option = random.choice("BC")
        amount = random.randrange(200, 500)
        body = "!bet {} {} {}  \nOn behalf of testuser{}".format(bet_id, option, amount, i)
        take_comment = offer_comment.reply(body)
        take_comment.author = "testuser{}".format(i)
        parse_comment(take_comment)
    winner = offer_comment.reply("!bet {} A 300  \nOn behalf of testwinner".format(bet_id))
    winner.author = "testwinner"
    parse_comment(winner)

    judge_comment = offer_comment.reply("!call_bet {} A  \nOn behalf of testjudge".format(bet_id))
    judge_comment.author = "testjudge"
    parse_comment(judge_comment)
    cur.execute("""
        SELECT * FROM bets WHERE cat_id = ?
        """, ("TEST", ))
    all_bets = cur.fetchall()
    body = ""
    for b in all_bets:
        bet_id, bet, author, created, end, reveal, source, ended, cat_id = b

        text = "Created by: {}, [source](/comments/{})  \n\n".format(author, source)
        text += "Expires: {}, Reveal: {}\n\n".format(human_date(end), human_date(reveal))
        text += "[{}:{}] **Bet**: {}  \n\n".format(cat_id, bet_id, bet)
        text += "|Label|Option|Multiplier|Probability|$ Bet|# Bets|\n"
        text += "|----:|:-----|:--------:|:---------:|:---:|:----:|\n"
        b_id = b[0]
        cur.execute("""
            SELECT * FROM options WHERE bet_id = ?
            """, (b_id,))
        options = cur.fetchall()
        for o in options:
            line = "|{}|{}|{}|{:.3f}|".format(o[4], o[1], o[3], 1/o[3])
            money_total = 0
            number_bets = 0
            print(o)
            cur.execute("""
                SELECT * FROM amounts WHERE option_id = ?
                """, (o[0],))
            amounts = cur.fetchall()
            for a in amounts:
                number_bets += 1
                money_total += a[3]
            line += "{}|{}|\n".format(money_total, number_bets)
            text += line

        text += "\n\n----------------\n\n"
        body += text
    submission.reply(body)

def scan(submission):
    submission.comment_sort = "old"
    for comment in submission.comments.list():
        if hasattr(comment, "removed") and comment.removed: continue
        parse_comment(comment)

#TODO: decorator for footer
def reply_error(error, comment):
    footer = "---------  \nTVBetBot"
    text = ""
    text += "Syntax Error: {}  \n".format(error)
    text += "Please see: [wiki for creating an offer]\n\n"
    text += footer
    print(text)
def parse_comment(comment):
    print(comment.body[:50])
    text = comment.body.split()
    if text[0] == "!offer_bet":
        try: handle_offer(comment)
        except OfferSyntaxError as e:
            reply_error(e, comment)
    if text[0] == "!bet":
        try: handle_bet(comment)
        except Error as e:
            reply_error(e, comment)
    if text[0] == "!call_bet":
        try: handle_call(comment)
        except Error as e:
            reply_error(e, comment)
                
#submission = reddit.submission(id="80a8c9")
#nuke_it_all(submission)
#rebuild(submission)
def shutdown(signum, frame):
    import sys
    print(signum, frame)
    sys.exit()
    raise Exception("shutting down!")
def read_everything(subname):
    i = 0
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
    for comment in reddit.subreddit(subname).stream.comments():
        if hasattr(comment, "removed") and comment.removed: continue
        print(i)
        parse_comment(comment)
        i += 1
        
submission = reddit.submission(id="80a8c9")
nuke_database()
rebuild_database()
#scan(submission)
#nuke_it_all(submission)
#rebuild(submission)
subname = "mrrobot+politics"
read_everything(subname)
