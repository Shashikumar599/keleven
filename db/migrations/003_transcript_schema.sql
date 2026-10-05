-- Transcript tables. Design and reasoning: docs/schema.md
-- Only aired scenes are loaded; cleaning history stays in data/processed/*.parquet.

CREATE TABLE IF NOT EXISTS episodes (
  season   int  NOT NULL,
  episode  int  NOT NULL,
  title    text NOT NULL,
  PRIMARY KEY (season, episode)
);

CREATE TABLE IF NOT EXISTS lines (
  id        int  PRIMARY KEY,              -- original script order from the dataset
  season    int  NOT NULL,
  episode   int  NOT NULL,
  scene     int  NOT NULL,                 -- aired scene order within the episode: 1..N, no gaps
  speaker   text NOT NULL,                 -- cleaned name
  text      text NOT NULL,                 -- single source of truth: dialogue with [directions] in place
  dialogue  text GENERATED ALWAYS AS (
              btrim(regexp_replace(regexp_replace(text, '\[[^\]]*\]', ' ', 'g'), '\s+', ' ', 'g'))
            ) STORED,                      -- speech only; empty for direction-only lines
  FOREIGN KEY (season, episode) REFERENCES episodes
);

-- Flat view for reading and (later) text-to-SQL: adds the episode title and the directions.
CREATE OR REPLACE VIEW lines_full AS
SELECT l.id, l.season, l.episode, e.title, l.scene,
       l.speaker, l.text, l.dialogue,
       array_to_string(ARRAY(SELECT m[1] FROM regexp_matches(l.text, '\[([^\]]*)\]', 'g') AS m), ' | ') AS directions
FROM lines l
JOIN episodes e USING (season, episode);
