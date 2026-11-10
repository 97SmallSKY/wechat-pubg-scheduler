CREATE TABLE settings (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  config TEXT NOT NULL
);
--> statement-breakpoint


CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  scheduled_day TEXT UNIQUE,
  report_day TEXT NOT NULL,
  config TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('queued','running','previewed','failed')),
  started_at TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  result TEXT
);
--> statement-breakpoint

CREATE TABLE runner (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  last_seen TEXT NOT NULL
);
