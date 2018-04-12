#!/usr/bin/env python3
import time
import praw
import prawcore
import dateparser 
import configparser
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

    Closes: [Date]  
    Reveal: [Date]  
    Category: [cat_id]"""

    def parse_offer():
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
            if line.lower().startswith("closes:"):
                if end_date:
                    raise OfferSyntaxError("Only one close date allowed.")
                end_date = dateparser.parse(line[7:], \
                    settings = {"RETURN_AS_TIMEZONE_AWARE" : True, "TIMEZONE" : "UTC"})
            if line.lower().startswith("reveal:"):
                if reveal_date:
                    raise OfferSyntaxError("Only one reveal date allowed.")
                reveal_date = dateparser.parse(line[7:], \
                    settings = {"RETURN_AS_TIMEZONE_AWARE" : True, "TIMEZONE" : "UTC"})
            if line.lower().startswith("category:"):
                if category:
                    raise OfferSyntaxError("Only one category allowed.")
                line = line.lower()
                category = line.lstrip("category:").strip()
        if not end_date:
            raise OfferSyntaxError("Invalid close date")
        if not reveal_date:
            raise OfferSyntaxError("Invalid reveal date.")
        if not category: 
            raise OfferSyntaxError("Must include category tag")
        response = (offer, category, end_date, reveal_date, confirmed)
        return response
    
    def offer_fixer():
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
    

    SQL.check_player(comment.author)
    offer, category, end_date, reveal_date, options = parse_offer( )
    cat_id, end_date, reveal_date = offer_fixer()
    
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    bet_id = SQL.add_offer(offer, cat_id, comment.author.name, int(comment.created_utc), \
        end_date, reveal_date, source, options)
    print(offer, cat_id, comment.author.name, int(comment.created_utc), end_date, reveal_date, source, options)
    print("the bet id is: {}".format(bet_id))
    
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for e, o in enumerate(options):
        SQL.add_option(o[0], bet_id, o[1], labels[e])
    
    update_hub(cat_id)
    my_sender = sender(reply_offer_bet,  comment)
    my_sender(bet_id)

def handle_bet(comment):
    """This handles a comment of someone taking a bet.
    First it parses a comment, and raises exceptions for syntax error
    or illegality. 
    Then it updates tables in database, updates hub, and repliess to comment.

    Syntax:

    !bet_take [bet_id] [option_label] [amount]"""
    #TODO: add  numerous bets from same person
    def parse_bet():
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
    bet_id, option, amount = parse_bet()
    bet_info = SQL.bet_info(bet_id)
    if not bet_info:
        raise Error("bet doesn't exist.")
    print("bet exists")
    cat_id = bet_info[6]
    closed = bet_info[7]
    if closed:
        raise Error("The best is closed.")
    print("bet's opened")
    option_id = SQL.find_option(bet_id, option)
    if not option_id: 
        raise Error("Option does not exist.")

    name = comment.author.name
    source = "{}//{}".format(comment.link_id[3:], comment.id)
    SQL.check_player(comment.author)
    if not SQL.check_if_enough_money(name, amount):
        raise Error("You don't have enough money.")
    print("enough money")
    SQL.take_bet(name, option_id, amount, source)
    SQL.change_bank(name, -amount)
    update_hub(cat_id)
    my_sender = sender(reply_to_bet, comment.author.name)
    my_sender(name, amount, option_id, bet_id, option)
    
def handle_call(comment):
    """This handles a comment of a judge calling a bet.
    First it parses the comment, and raises exceptions for syntax errors
    or illegality.
    Then it updates the databases, awarding wins
    Then it updates the hub, and replies to the comment.

    Syntax:

    !bet_call [bet_id] [option_label]
    """
    def parse_call():
        """parses a !bet_call comment, returns relevant values."""
        split = comment.body.split()
        bet_id = split[1]
        label = split[2].upper()
        return bet_id, label
    bet_id, label = parse_call()
    bet_info = SQL.bet_info(bet_id)
    if not bet_info: 
        raise Error("You called a bet that doesn't exist.")
    creator = bet_info[1]
    cat_id = bet_info[6]
    closed = bet_info[7]
    # invalid/bad bet offer
    if label.lower() == "void":
       void(bet_id) 
       return
    if not closed:
        raise Error("The bet is still open. If revealed early, maybe void instead.")
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
        for amount, player in SQL.derive_pot_from_bets(o):
            # check if the player is even still on reddit
            try:
                reddit.redditor(player).fullname
            except prawcore.exceptions.NotFound:
                continue
            pot += amount
    pot_before = pot
    profit = 0
    #TODO: make a public comment saying who won
    #win_comment = comment.reply("{} declared {} to be the winner!".format(comment.author, label))
    for winner in winners:
        print(winner)
        name, amount = winner[2:4]
        try:
            reddit.redditor(name).fullname
        except prawcore.exceptions.NotFound:
            continue
        winnings = int(amount * multiplier)
        SQL.change_bank(name, winnings)
        pot -= winnings
        profit += (winnings / 10)
        my_sender = sender(lambda x, y: "You won {} betting on {}!".format(x, y), name)
        my_sender(winnings, bet_id)
    creator_new_worth = amount_owned_by_creator + profit + pot
    SQL.change_bank(creator, profit + pot)
    SQL.end_bet(bet_id)
    print("We came through to the end!")
    #TODO: uncommenet
    update_hub(cat_id)
    








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
        submission = reddit.subreddit(hub_subreddit).submit(title=title, selftext=body)
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

#TODO: decorator for footer
def reply_error(error):
    """Handles an error in a comment by replying to the comment saying what's wrong."""
    text = ""
    text += "Syntax Error: {}  \n".format(error)
    text += "Please see: [wiki for creating an offer]\n\n"
    return text
def handle_add_judge(comment):
    # check if person adding judge is owner
    # check if user exists
    # check if category exists
    # update database
    # notify judges and person
    try:
        assert comment.author.name == owner
    except:
        raise Exception("You are not the owner of the bot")
    try:
        _, player, category = comment.body.split()[:4]
    except: 
        raise Exception("Bad syntax")
    try:
        reddit.redditor(player).fullname
    except prawcore.exceptions.NotFound:
        raise Exception("Redditor doesn't exist.")
    try:
        SQL.get_cat_id(category)
    except:
        raise Exception("category doesn't exist.")
    SQL.remove_judge(category, player)
    SQL.add_judge(category, player)
    print("{} added to {}'s judges".format(player, category))




def parse_comment(comment):
    """Parses a comment, handling them of it contains a command as the first word."""
    text = comment.body.split()
    error_handler = sender(reply_error, comment)
    if text[0] == "!offer_bet":
        try: handle_offer(comment)
        except OfferSyntaxError as e:
            error_handler(str(e))
    if text[0] == "!bet":
        try: handle_bet(comment)
        except Error as e:
            error_handler(str(e))
    if text[0] == "!call_bet":
        try: handle_call(comment)
        except Error as e:
            print(str(e))
            error_handler(str(e))
    if text[0] == "!tvbetbot_add_judge":
        try:
            handle_add_judge(comment)
        except Error as e:
            error_handler(str(e))
                
def check_if_changed_status(status):
    if status == "closed":
        targets = SQL.get_next_closing_bets()
        index = 4
    elif status == "revealed":
        targets = SQL.get_next_revealed_bets()
        index = 5
    elif status == "two days":
        targets = SQL.get_next_to_be_judged()
        index = 5
    else: raise
    now = datetime.datetime.now(datetime.timezone.utc)
    for t in targets:
        bet_id = t[0] 
        target_time = datetime.datetime.fromtimestamp(int(t[index]), datetime.timezone.utc)
        if status == "two days":
            target_time = target_time + datetime.timedelta(days=2)
        if (target_time - now).total_seconds() <= 0:
            if status == "two days":
                SQL.cur.execute("""
                    UPDATE bets SET ended = 1
                    WHERE bet_id = ?
                    """, (bet_id,))
                SQL.con.commit()
                void(bet_id)

            if status == "revealed":
                notify_judges(t)
                SQL.cur.execute("""
                    UPDATE bets SET revealed = '1'
                    WHERE bet_id = ?
                    """, (bet_id,))
                SQL.con.commit()
                
            elif status == "closed":
                SQL.cur.execute("""
                    UPDATE bets set closed = '1'
                    WHERE bet_id = ?
                    """, (bet_id,))
                SQL.con.commit()

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
def void(bet_id):
    SQL.cur.execute("""
        SELECT option_id FROM options
        WHERE bet_id = ?
        """, (bet_id,))
    option_response = SQL.cur.fetchall()
    for option in option_response:
        option_id = option[0]
        SQL.cur.execute("""
            SELECT * FROM amounts
            WHERE option_id = ?
            """, (option_id,))
        response = SQL.cur.fetchall()
        for amount in response:
            name = amount[2]
            amount = amount[3]
            SQL.change_bank(name, amount)
            SQL.cur.execute("""
                DELETE FROM amounts 
                WHERE option_id = ?
                """, (option_id,))
        SQL.con.commit()

    
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
        previous = datetime.datetime.now()
        try:
            for comment in reddit.subreddit(subname).stream.comments(pause_after=0):
                # the stream will automatically list the last 100 comments.  This is annoying behavior and
                # may result in comments being parsed twice.
                if i < 100:
                    i += 1
                    continue
                i += 1
                if comment is None:
                    now = datetime.datetime.now()
                    previous = now
                    check_if_changed_status("closed")
                    check_if_changed_status("revealed")
                    check_if_changed_status("two days")
                    continue
                else:
                    parse_comment(comment)
                if i % 500 == 0:
                    print("#{} @ {}".format(i, datetime.datetime.now()))
                if hasattr(comment, "removed") and comment.removed: 
                    continue
        except prawcore.exceptions.RequestException:
            time.sleep(10)
    return message
def sender(function, target):    
    if type(target) is praw.models.reddit.comment.Comment:
        target_type = "comment"
    else:
        target_type = "redditor"
        print("TARGET: {}".format(target))
        print("TARGETp2: {}".format(type(target)))
        target = reddit.redditor(target)
    def my_wrapper(*myvars):
        text = function(*myvars)
        text += "\n\n========\n\n"
        text += "tvbetbot (beta) | [subreddit](http://www.reddit.com/r/tvbets) | [Tutorial](https://www.reddit.com/r/TVbets/comments/85gahv/tutorial/) | [Questions/Issues](https://www.reddit.com/message/compose?to={})  \n".format(owner)
        if target_type == "comment":
            try:
                target.reply(text)
            except praw.exceptions.APIException: pass
        else:
            try: 
                target.message("TVBetBot notification", text)
            except praw.exceptions.APIException: pass

    return my_wrapper
import sys
if __name__ == "__main__":
    owner, hub_subreddit, subs = SQL.get_admin_info()
#    comment = reddit.comment("dx4iy2q")
#    offer_comment = reddit.comment("dwsjy5c")
#    bet_comment = reddit.comment("dvwd7d4")
#    call_comment = reddit.comment("dx831lh")
#    print(offer_comment.body)
#    print(bet_comment.body)
#    print(call_comment.body)
#    parse_comment(offer_comment)
#    parse_comment(bet_comment)
#    parse_comment(call_comment)

#    sys.exit()
    read_everything(subs)
other = """
TODO: judges can bet, but whichever judge calls it won't get paid out, and will
be refunded his money back
Handle PMs
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

    

