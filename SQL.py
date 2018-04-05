import sqlite3 as sql
def check_player(author):
    name = author.name
    cur.execute("SELECT * FROM bank WHERE player = ? ", (name,))
    results = cur.fetchall()
    if not results:
        cur.execute("INSERT INTO bank VALUES (?, ?, ?)", (name , 10000, 0))
        con.commit()
def end_bet(bet_id):
    cur.execute("""UPDATE bets SET ended = '1' WHERE bet_id = ?
        """, (bet_id,))
    con.commit()

def get_cat_id(category):
    cur.execute("""
        SELECT 1 FROM categories 
        WHERE upper(cat_id) = ?
        """, (category.upper(),))

    response = cur.fetchone()
    if not response: raise Exception
    return response[0]
def add_offer(bet, cat_id, author, created, end, reveal, source, options):
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
def add_option(option_text, bet_id, multiplier, label):
    cur.execute("""
        INSERT INTO options 
            (option, bet_id, multiplier, label) 
        VALUES
            (?, ?, ?, ?)
        """, (option_text, bet_id, multiplier, label))
    con.commit()


def find_option(bet_id, label):
    cur.execute("""
        SELECT option_id FROM options
        WHERE bet_id = ? AND label = ?
        """, (bet_id, label))
    result = cur.fetchone()
    if result:
        return result[0]
    else:
        return None
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
def bet_info(bet_id):
    cur.execute("""
        SELECT bet, creator, created, expires, reveal, ended, cat_id, closed, revealed
        FROM bets WHERE bet_id = ?
        """, (bet_id,))
    result = cur.fetchone()

    return result

def option_info(bet_id):
    cur.execute("""
        SELECT * FROM options WHERE bet_id = ?
        """, (bet_id,))
    result = cur.fetchall()
    return result
def get_specific_option_info(option_id):
    cur.execute("""
        SELECT * FROM options WHERE option_id = ?
        """, (option_id,))
    result = cur.fetchone()
    return result
def amounts_winners(option_id):
    cur.execute("""
        SELECT * FROM amounts WHERE option_id = ?
        """, (option_id,))
    result = cur.fetchall()
    return result
def get_judges(cat_id):
    cur.execute("""
        SELECT user FROM judges WHERE cat_id = ?
        """, (cat_id,))
    result = cur.fetchall()
    result = [x[0] for x in result]

    return result
def get_balance(creator):
    cur.execute("""
        SELECT balance FROM bank
        WHERE player = ?
        """, (creator,))
    response = cur.fetchone()[0]
    return response
def change_bank(name, winnings):
    cur.execute("""
        UPDATE bank 
        SET balance = balance + ?
        WHERE player = ?
        """, (winnings, name))
    con.commit()
    pass
def derive_pot_from_bets(opt_id):
    cur.execute("""
        SELECT amount, bettor FROM amounts
        WHERE option_id = ?
        """, (opt_id,))
    result = cur.fetchall()
#    if not result: return 0
#    result = sum([x[0] for x in result])
    return result

def get_next_closing_bets():
    cur.execute("""
        SELECT * FROM bets 
        WHERE ended = '0'
        AND closed = '0'
        ORDER BY expires ASC
        """)
    result = cur.fetchall()
    return result
def get_next_revealed_bets():
    cur.execute("""
        SELECT * FROM bets
        WHERE ended = '0'
        AND revealed = '0'
        ORDER BY reveal ASC
        """)
    result = cur.fetchall()
    return result
def get_next_to_be_judged():
    cur.execute("""
        SELECT * FROM bets
        WHERE ended = '0'
        AND revealed = '1'
        ORDER BY reveal ASC
        """)
    result = cur.fetchall()
    return result
con = sql.connect("example.sql")
cur = con.cursor()
