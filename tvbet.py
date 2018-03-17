#!/usr/bin/env python3
import time
import praw
import dateparser 
import sqlite3 as sql
import random
import signal
import datetime
import socket
import sys
import SQL
class Error(Exception):
    pass
class OfferSyntaxError(Error):
    def __init__(self, value):
        self.value = value

class OfferLegalityError(Error):
    def __init__(self, value):
        self.value = value


reddit = praw.Reddit("bot1")
def human_date(timestamp):
    return datetime.datetime.fromtimestamp(timestamp, datetime.timezone.utc).strftime("%b-%d-%Y %H:%M UTC")


def handle_offer(comment):
    """Handles a comment offering a bet.
    First parses the comment, raising exceptions if it's invalid syntax.
    Then raises exceptions if command is illegal.
    Then it adds the bet to the relevant tables, updates the hub, 
    and replies to the comment.

    Syntax:

    !offer_bet [bet]

    * [mult] [option]
    * [mult] [option]

    Ends: [Date]  
    Reveal: [Date]  
    Category: [cat_id]"""
    
    SQL.check_player(comment.author)
    offer, category, end_date, reveal_date, options = parse_offer(comment)
    cat_id, end_date, reveal_date = offer_fixer(end_date, reveal_date, category)
    
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    bet_id = SQL.add_offer(offer, cat_id, comment.author.name, int(comment.created_utc), \
        end_date, reveal_date, source, options)
    
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for e, o in enumerate(options):
        SQL.add_option(o[0], bet_id, o[1], labels[e])
    
    update_hub(cat_id)
#    text = reply_offer_bet(bet_id)
    my_sender = sender(reply_offer_bet,  comment)
    my_sender(bet_id)
#    comment.reply(text) #TODO
    #print("REPLY TO COMMENT: \n\n{}".format(text))

def handle_bet(comment):
    """This handles a comment of someone taking a bet.
    First it parses a comment, and raises exceptions for syntax error
    or illegality. 
    Then it updates tables in database, updates hub, and repliess to comment.

    Syntax:

    !bet_take [bet_id] [option_label] [amount]"""
    #TODO: add  numerous bets from same person
    bet_id, option, amount = parse_bet(comment)
    bet_info = SQL.bet_info(bet_id)
    if not bet_info:
        raise Error("bet doesn't exist.")
    cat_id = bet_info[6]
    option_id = SQL.find_option(bet_id, option)
    if not option_id: 
        raise Error("Option does not exist.")

    name = comment.author.name
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    SQL.check_player(comment.author)
    if not SQL.check_if_enough_money(name, amount):
        raise Error("You don't have enough money.")
    SQL.take_bet(name, option_id, amount, source)
    SQL.change_bank(name, -amount)
    update_hub(cat_id)
    my_sender = sender(reply_to_bet, comment.author)
    my_sender(name, amount, option_id, bet_id, option)
#    text = reply_to_bet(name, amount, option_id, bet_id, option)
#    comment.reply(text)
    
def handle_call(comment):
    """This handles a comment of a judge calling a bet.
    First it parses the comment, and raises exceptions for syntax errors
    or illegality.
    Then it updates the databases, awarding wins
    Then it updates the hub, and replies to the comment.

    Syntax:

    !bet_call [bet_id] [option_label]
    """
    bet_id, label = parse_call(comment)
    bet_info = SQL.bet_info(bet_id)
    if not bet_info: 
        raise Error("You called a bet that doesn't exist.")
    creator = bet_info[1]
    cat_id = bet_info[6]
    option_id = SQL.find_option(bet_id, label)
    if not option_id: 
        raise Error("You called an option that doesn't exist.")
    if not comment.author.name in SQL.get_judges(cat_id):
        raise Error("You're not a judge for this category.")

    # Now that everything is legal, we can get to the meat of it.
    amount_owned_by_creator = SQL.get_balance(creator)
    winners = SQL.amounts_winners(option_id)
    multiplier = SQL.get_specific_option_info(option_id)[3]
    all_options = [x[0] for x in SQL.option_info(bet_id)]
    pot = 0
    for o in all_options:
        pot += SQL.derive_pot_from_bets(o)
    pot_before = pot
    profit = 0
    #TODO: inform everyone of their winnings
    win_comment = comment.reply("{} declared {} to be the winner!".format(comment.author, label))
    for winner in winners:
        name, amount = winner[2:4]
        winnings = int(amount * multiplier)
        SQL.change_bank(name, winnings)
        pot -= winnings
        profit += (winnings / 10)
        reddit.redditor(winner).message("You won {} betting on {}!".format(winnings, bet_id))
    creator_new_worth = amount_owned_by_creator + profit + pot
    SQL.change_bank(creator, profit + pot)
    SQL.end_bet(bet_id)
    update_hub(cat_id)
    

def parse_offer(comment):
    """parses an !offer_bet command, returning the relevant values"""
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
    if "|" in offer:
        raise OfferSyntaxError("vertical bars, '|', are not allowed.")

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
        if "|" in option:
            raise OfferSyntaxError("vertical bars, '|', are not allowed.")
        confirmed.append((option, odds))
    end_date = None
    reveal_date = None
    category = None
    for line in lines:
        if line.lower().startswith("end:"):
            end_date = dateparser.parse(line[4:], \
                settings = {"RETURN_AS_TIMEZONE_AWARE" : True, "TIMEZONE" : "UTC"})
        if line.lower().startswith("reveal:"):
            reveal_date = dateparser.parse(line[7:], \
                settings = {"RETURN_AS_TIMEZONE_AWARE" : True, "TIMEZONE" : "UTC"})
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

def parse_bet(comment):
    """Parses a !bet_take comment, returns relevant values."""
    lines = comment.body.split("\n")
    first_line = lines[0].split()
    if len(first_line) != 4:
        raise Error("Command requires exactly four arguments")
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
    """parses a !bet_call comment, returns relevant values."""
    split = comment.body.split()
    bet_id = split[1]
    label = split[2].upper()
    return bet_id, label

def reply_offer_bet(bet_id):
    """Generates the text for the comment to reply to a !bet_offer comment."""
    bet, creator, created, expires, reveal, ended, cat_id, closed, revealed = \
        SQL.bet_info(bet_id)
    options = SQL.option_info(bet_id)
    text = ""
    text += "--------  \n\n"
    text += "[{}:{}] **Bet**: {}  \n\n\n".format(cat_id, bet_id, bet)
    text += "|Label|Option|Odds|Probability|\n"
    text += "|----:|:-----|:--:|:---------:|\n"
    for o in SQL.option_info(bet_id):
        _, option, _, multiplier, label = o
        probability = 1/multiplier
        text += "|**{}**|{}|{}|{:.3f}|\n".format(label, option, multiplier, probability)
    text += "\n\n{}".format(human_date(expires))
    return text

def reply_to_bet(name, amount, option_id, bet_id, option_label):
    """Generates the text for the comment to reply to a !bet_take comment."""
    multiplier = SQL.get_specific_option_info(option_id)[3]
    new = SQL.get_balance(name)
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
    return text


    
def offer_fixer(end_date, reveal_date, category):
    """Transforms dates and category id into better forms"""

    now = datetime.datetime.now(datetime.timezone.utc)
    if (reveal_date - now).total_seconds() < 0:
        raise OfferLegalityError("Reveal date set in past.")
    if (end_date - now).total_seconds() < 0:
        raise OfferLegalityError("End date set in past.")
    if (reveal_date - end_date).total_seconds() < 0:
        raise OfferLegalityError("End date occurs after reveal date.")
    
    cat_id = SQL.get_cat_id(category)
    cat_id = category.upper()
    response = (cat_id, end_date.timestamp(), reveal_date.timestamp())
    return response

def nuke_thread(submission):

    submission.comment_sort = "old"
    for comment in submission.comments.list():
        if not comment.removed:
            comment.mod.remove()
def nuke_database():
    #cur.execute("DELETE FROM categories")
    SQL.cur.execute("DELETE FROM bets")
    SQL.cur.execute("DELETE FROM bank")
    SQL.cur.execute("DELETE FROM amounts")
    SQL.cur.execute("DELETE FROM options")
    SQL.cur.execute("DELETE FROM judges")
    SQL.con.commit()

def nuke_it_all(submission):
        
    nuke_thread(submission)
    nuke_database()
def rebuild_database():
    #cur.execute("INSERT INTO categories VALUES ('TEST', 'A test category', NULL)")
    SQL.cur.execute("INSERT INTO judges VALUES ('sje46', 'TEST')")
    SQL.con.commit()

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
    SQL.cur.execute("""SELECT MAX(bet_id) FROM bets""")
    bet_id2 = SQL.cur.fetchone()[0]
    
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

    parse_comment(offer_comment)
    SQL.cur.execute("""SELECT MAX(bet_id) FROM bets""")
    bet_id = SQL.cur.fetchone()[0]
    for i in range(0):
        option = random.choice("BC")
        amount = random.randrange(200, 500)
        body = "!bet {} {} {}  \nOn behalf of testuser{}".format(bet_id, option, amount, i)
        take_comment = offer_comment.reply(body)
        take_comment.author = "sje46".format(i)
        parse_comment(take_comment)
    winner = offer_comment.reply("!bet {} A 300  \nOn behalf of testwinner".format(bet_id))
    winner.author = "sje46"
    parse_comment(winner)

    judge_comment = offer_comment.reply("!call_bet {} A  \nOn behalf of testjudge".format(bet_id))
    judge_comment.author = "sje46"
    parse_comment(judge_comment)

def create_hub_entry(b):
    """Creates a single entry for a hub."""
    bet_id, bet, author, created, end, reveal, source, ended, cat_id, closed, revealed = b
    text = "**bet_id**: {}  \n".format(bet_id)
    text += "**Bet**: {}  \n\n".format(bet)
    text += "|Label|Option|Multiplier|Probability|$ Bet|# Bets|\n"
    text += "|----:|:-----|:--------:|:---------:|:---:|:----:|\n"
    SQL.cur.execute("""
        SELECT * FROM options WHERE bet_id = ?
        """, (bet_id,))
    options = SQL.cur.fetchall()
    for o in options:
        option_text = o[1].replace("|", "\|")
        line = "|{}|{}|{}|{:.3f}|".format(o[4], option_text, o[3], 1/o[3])
        money_total = 0
        number_bets = 0
        SQL.cur.execute("""
            SELECT * FROM amounts WHERE option_id = ?
            """, (o[0],))
        amounts = SQL.cur.fetchall()
        for a in amounts:
            number_bets += 1
            money_total += a[3]
        line += "{}|{}|\n".format(money_total, number_bets)
        text += line
    text += "**Created by**: {}, [source](/comments/{})  \n\n".format(author, source)
    text += "**Closes**: {}, **Reveal**: {}\n\n".format(human_date(end), human_date(reveal))
    
    text += "\n\n----------------\n\n"
    return text 
def scan(submission):
    """Scans a submission for relevant comments, handles them."""
    submission.comment_sort = "old"
    for comment in submission.comments.list():
        if hasattr(comment, "removed") and comment.removed: continue
        print(comment)
        parse_comment(comment)

#TODO: decorator for footer
def reply_error(error, comment):
    """Handles an error in a comment by replying to the comment saying what's wrong."""
    footer = "---------  \nTVBetBot"
    text = ""
    text += "Syntax Error: {}  \n".format(error)
    text += "Please see: [wiki for creating an offer]\n\n"
    text += footer

def parse_comment(comment):
    """Parses a comment, handling them of it contains a command as the first word."""
    text = comment.body.split()
    if text[0] == "!offer_bet":
        try: handle_offer(comment)
        except OfferSyntaxError as e:
            reply_error(e, comment)
    if text[0] == "!bet":
        try: handle_bet(comment)
        except Error as e:
            reply_error(e, comment)
    if text[0] == "!call_beta":
        try: handle_call(comment)
        except Error as e:
            reply_error(e, comment)
                
def update_hub(cat_id): 
    """Updates the hub if any of the bets change.  Edits the submission directly."""
    #TODO: escape all special characters
    SQL.cur.execute("""SELECT * FROM bets WHERE cat_id = ? 
        AND ended = '0'
        AND closed = '0'
        ORDER BY expires ASC
        """, (cat_id,))
    open_bets = SQL.cur.fetchall()
    SQL.cur.execute("""SELECT * FROM bets WHERE cat_id = ?
        AND ended = '0'
        AND closed = '1'
        ORDER BY expires ASC
        """, (cat_id,))
    closed_bets = SQL.cur.fetchall()
    body = ""
    body = "Open Bets Closing Soon\n========\n\n"
    length = len(body)
    for b in open_bets:
        entry = create_hub_entry(b)
        length += len(entry)
        if length > 40000:
            #TODO: overflow into comments or wiki
            break
        body += entry
    body += "Closed bets ending soon\n=======\n\n"
    for b in closed_bets:
        entry = create_hub_entry(b)
        length += len(entry)
        if length >= 40000:
            break
        body += entry
    SQL.cur.execute("""SELECT description, hub FROM categories WHERE cat_id = ?
        """, (cat_id,))
    description, hub = SQL.cur.fetchone()
    if not hub:
        title = "Active '{}' bets".format(description)
        submission = reddit.subreddit("sje46").submit(title=title, selftext=body)
        source = str(submission.id)
        SQL.cur.execute("""UPDATE categories SET hub = ? 
            WHERE cat_id = ?
            """, (source, cat_id))
        SQL.con.commit()
    else:
        #TODO: what if the submission's too old?
        submission = reddit.submission(id=hub)
        if submission.selftext != body:
            submission.edit(body)
#    print(body)
def check_if_changed_status(status):
    if status == "closed":
        targets = SQL.get_next_closing_bets()
        index = 4
    elif status == "revealed":
        targets = SQL.get_next_revealed_bets()
        index = 5
    else: raise
    now = datetime.datetime.now(datetime.timezone.utc)
    for t in targets:
         
        target_time = datetime.datetime.fromtimestamp(int(t[index]), datetime.timezone.utc)
        if (target_time - now).total_seconds() <= 0:
            SQL.cur.execute("""UPDATE bets SET {} = '1'
                WHERE bet_id = ?
                """.format(status), (t[0],))
            SQL.con.commit()
            if status == "revealed":
                print("JUDGES PLEASE JUDGE THIS BET!!!!")
                notify_judges(t)
                
            elif status == "closed":
                print("bet is now closed.")
            update_hub(t[8])
        else:
            break
def notify_judges(bet):
    #TODO: if not judged within two days, void
    SQL.cur.execute("""
        SELECT * FROM judges
        WHERE cat_id = ?
        """, (bet[8],))
    response = SQL.cur.fetchall()
    source = bet[6]
    for judge in response:
        title = "Judge request for {}.{}".format(bet[8], bet[0])
        message = "Please call the bet for {}.{}. [Source.](/comments/{})\n\n".format(bet[8], bet[0], source)
        message += bet[1] + "\n\n"
        message += "If not called within two days, it will be voided and all bets will be refunded."

        reddit.redditor(judge[0]).message(title, message)

def shutdown(signum, frame):
    """Shuts down the whole thing cleanly if you hit ctrl+c"""
    import sys
    sys.exit()
    raise Exception("shutting down!")
def read_everything(subname):
    """Parse every comment in the sub(s)"""
    i = 1
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    while True: 
        try:
            for comment in reddit.subreddit(subname).stream.comments(pause_after=0):# or None? TODO
                if comment is None:
                    check_if_changed_status("closed")
                    check_if_changed_status("revealed")
                    continue
                if i % 100 == 0:
                    print(i, datetime.datetime.now())
                i += 1
                if hasattr(comment, "removed") and comment.removed: continue
        except prawcore.exceptions.RequestException:
            time.sleep(10)
def message_maker(a, b):
    message = "first param: {}, second: {}".format(a, b)
    return message
def message_maker_2(a, b, c): 
    message = "first param: {}, second: {} third: {}".format(a, b, c)
    return message
def sender(function, target):    
    if type(target) is praw.models.reddit.comment.Comment:
        target_type = "comment"
    else:
        target_type = "redditor"
    def my_wrapper(*myvars):
        text = function(*myvars)
        text += "\n\n========\n\n"
        text += "tvbetbot | [subreddit](subreddit) | [Tutorial](tutorial) | [Questions/Issues](Issues)  \n"
        if target_type == "comment":
            target.reply(text)
        else:
            target.message("TVBetBot notification", text)

    return my_wrapper
    
        
import prawcore
submission = reddit.submission(id="80a8c9")
subname = "politics+sje46"
nuke_database()

rebuild_database()
#read_everything(subname)
scan(submission)
#read_everything(subname)
#nuke_it_all(submission)
#rebuild(submission)
#subname = "mrrobot+politics"
#read_everything(subname)
other = """
!bet_offer
    to offer a bet
!bet_take
    to take a bet
!bet_call
    to call a bet
!bet_void
    for judge to annul a bet
!bet_edit [bet_id]
    to tell the bot to reload the bet
    refunding all people who took the bet before
    but pm'ing them about the new bet
    must be done within 30 minutes
!bet_cancel
    must be done within 30 minutes
    all are refunded
!bet_info
    information about a bet
!bet_bank
    tells you how much moeny a player has
!bet_report
    reports a bet directly to the judges
events:
    close
    reveal
    2-days
        h
"""

    

