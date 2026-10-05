-- Chunks: the units retrieval searches over. Design and reasoning: docs/schema.md
-- Several chunking strategies can live side by side, one chunk_set each.

CREATE TABLE IF NOT EXISTS chunk_sets (
  chunk_set_id  int  PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  name          text NOT NULL UNIQUE,      -- e.g. 'pack_250t_3s_80min'
  params        jsonb NOT NULL,            -- the settings that produced this set
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id       int  PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  chunk_set_id   int  NOT NULL REFERENCES chunk_sets ON DELETE CASCADE,
  season         int  NOT NULL,
  episode        int  NOT NULL,
  position       int  NOT NULL,            -- order within the episode; neighbours are position +/- 1
  first_line_id  int  NOT NULL REFERENCES lines,
  last_line_id   int  NOT NULL REFERENCES lines,   -- chunk = lines first..last in script order
  content        text NOT NULL,            -- snapshot of exactly what was embedded: header + "Speaker: text" lines
  token_count    int  NOT NULL CHECK (token_count > 0),
  FOREIGN KEY (season, episode) REFERENCES episodes,
  UNIQUE (chunk_set_id, season, episode, position),
  CHECK (first_line_id <= last_line_id)
);

-- Reading view: adds title, scene range and speakers, derived from the lines the chunk covers.
CREATE OR REPLACE VIEW chunks_full AS
SELECT c.chunk_id, s.name AS chunk_set, c.season, c.episode, e.title, c.position,
       l.scene_start, l.scene_end, l.speakers, l.n_lines,
       c.first_line_id, c.last_line_id, c.token_count, c.content
FROM chunks c
JOIN chunk_sets s USING (chunk_set_id)
JOIN episodes e USING (season, episode)
CROSS JOIN LATERAL (
  SELECT min(scene) AS scene_start, max(scene) AS scene_end,
         array_agg(DISTINCT speaker ORDER BY speaker) AS speakers, count(*) AS n_lines
  FROM lines
  WHERE id BETWEEN c.first_line_id AND c.last_line_id
) l;
