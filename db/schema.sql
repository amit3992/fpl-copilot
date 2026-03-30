CREATE TABLE IF NOT EXISTS session_state (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS transfer_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gameweek INTEGER,
    player_out TEXT,
    player_in TEXT,
    hit_taken INTEGER DEFAULT 0,
    net_gain_projected FLOAT,
    reasoning TEXT,
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
