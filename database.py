import sqlite3


DB_NAME = "signals.db"


def create_database():
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signal_time TEXT,
            symbol TEXT,
            initial_signal TEXT,
            signal TEXT,
            entry_price REAL,
            stop_loss REAL,
            take_profit REAL,
            score INTEGER,
            risk_reward REAL,
            risk_percent REAL,
            reward_percent REAL,
            result TEXT
        )
    """)

    connection.commit()
    connection.close()


def save_signal(
    signal_time,
    symbol,
    initial_signal,
    signal,
    entry_price,
    stop_loss,
    take_profit,
    score,
    risk_reward,
    risk_percent,
    reward_percent
):
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO signals (
            signal_time,
            symbol,
            initial_signal,
            signal,
            entry_price,
            stop_loss,
            take_profit,
            score,
            risk_reward,
            risk_percent,
            reward_percent,
            result
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        signal_time,
        symbol,
        initial_signal,
        signal,
        entry_price,
        stop_loss,
        take_profit,
        score,
        risk_reward,
        risk_percent,
        reward_percent,
        None
    ))

    connection.commit()
    connection.close()


def update_signal_result(signal_id, result):
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        UPDATE signals
        SET result = ?
        WHERE id = ?
    """, (
        result,
        signal_id
    ))

    connection.commit()
    connection.close()


def get_open_signals():
    connection = sqlite3.connect(DB_NAME)
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            id,
            signal_time,
            symbol,
            signal,
            entry_price,
            stop_loss,
            take_profit
        FROM signals
        WHERE result IS NULL
        ORDER BY id
    """)

    signals = cursor.fetchall()

    connection.close()

    return signals


if __name__ == "__main__":
    create_database()
    print("SQLite-база создана.")
