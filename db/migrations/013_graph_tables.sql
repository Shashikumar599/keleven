-- Graph tables (v3), layer 2: built from the stored extractions (episode_extractions, stage 'reviewed') and the character
-- linking result, by graph/build_graph.py. No LLM is involved, so a build can be thrown away and rebuilt at any time.
-- Design: docs/graph-design.md. A "build" is one run of the loader; everything below belongs to one build.
--
-- Local ids (c1, p1, e1, r1) only mean something inside one episode. A character is linked to an entity through
-- graph_characters.entity_name (the entity's normalised name, stable across rebuilds, so it is the key); relations and event participants are joined to entities through that link, so a wrong link
-- is fixed by rebuilding the link and no extracted fact changes. link_tier says how sure the link is:
--   certain   name recurs in 40+ episodes with one card per episode (graph/link_certain.py)
--   probable  full name, 3+ episodes, one card per episode (graph/link_tiers.py)
--   possible  one-word name, 3+ episodes, one card per episode; may be a role or several people
-- A card with no entity_name is unlinked: it stays a local node, found by name. graph_entity_links lists the named entities a
-- possible entity might be the same as ('possible_same'); it is never treated as a merge.

CREATE TABLE IF NOT EXISTS graph_builds (
  build_id        serial      PRIMARY KEY,
  label           text        NOT NULL UNIQUE,
  run_id          int         NOT NULL REFERENCES extraction_runs (run_id),   -- the extraction run read
  rules           jsonb       NOT NULL DEFAULT '{}',                           -- linking thresholds and input files
  counts          jsonb       NOT NULL DEFAULT '{}',
  created_at      timestamptz NOT NULL DEFAULT now()
);

-- The build that queries and views use; one row.
CREATE TABLE IF NOT EXISTS graph_current (
  only_row        boolean     PRIMARY KEY DEFAULT true CHECK (only_row),
  build_id        int         NOT NULL REFERENCES graph_builds (build_id)
);

CREATE TABLE IF NOT EXISTS graph_entities (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  name            text        NOT NULL,                                        -- normalised primary name; the key
  names           text[]      NOT NULL DEFAULT '{}',                           -- primary names merged into it
  tier            text        NOT NULL CHECK (tier IN ('certain', 'probable', 'possible')),
  cards           int         NOT NULL,
  episodes        int         NOT NULL,
  seasons         int[]       NOT NULL DEFAULT '{}',
  note            text,
  PRIMARY KEY (build_id, name)
);

-- A possible entity that might be the same person as a named one (david -> david wallace). Never a merge.
CREATE TABLE IF NOT EXISTS graph_entity_links (
  build_id        int         NOT NULL,
  entity_a        text        NOT NULL,
  entity_b        text        NOT NULL,
  kind            text        NOT NULL CHECK (kind IN ('possible_same')),
  PRIMARY KEY (build_id, entity_a, entity_b, kind),
  FOREIGN KEY (build_id, entity_a) REFERENCES graph_entities (build_id, name) ON DELETE CASCADE,
  FOREIGN KEY (build_id, entity_b) REFERENCES graph_entities (build_id, name) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS graph_characters (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  local_id        text        NOT NULL,
  names           text[]      NOT NULL,
  description     text        NOT NULL,
  present         boolean     NOT NULL,
  line_ids        int[]       NOT NULL DEFAULT '{}',
  entity_name     text,                                                        -- null when unlinked
  link_tier       text        CHECK (link_tier IN ('certain', 'probable', 'possible')),   -- null when unlinked
  PRIMARY KEY (build_id, season, episode, local_id),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode),
  FOREIGN KEY (build_id, entity_name) REFERENCES graph_entities (build_id, name)
);
CREATE INDEX IF NOT EXISTS graph_characters_entity_idx ON graph_characters (build_id, entity_name);
CREATE INDEX IF NOT EXISTS graph_characters_names_idx ON graph_characters USING gin (names);

CREATE TABLE IF NOT EXISTS graph_places (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  local_id        text        NOT NULL,
  name            text        NOT NULL,
  kind            text        NOT NULL,
  description     text        NOT NULL,
  line_ids        int[]       NOT NULL DEFAULT '{}',
  PRIMARY KEY (build_id, season, episode, local_id),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode)
);

CREATE TABLE IF NOT EXISTS graph_events (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  event_id        text        NOT NULL,
  text            text        NOT NULL,
  kind            text        NOT NULL,
  place_local_id  text,
  certainty       text        NOT NULL,
  importance      text        NOT NULL,
  line_ids        int[]       NOT NULL DEFAULT '{}',
  PRIMARY KEY (build_id, season, episode, event_id),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode),
  FOREIGN KEY (build_id, season, episode, place_local_id) REFERENCES graph_places (build_id, season, episode, local_id)
);
CREATE INDEX IF NOT EXISTS graph_events_text_idx ON graph_events USING gin (to_tsvector('english', text));

CREATE TABLE IF NOT EXISTS graph_event_participants (
  build_id        int         NOT NULL,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  event_id        text        NOT NULL,
  local_id        text        NOT NULL,
  role            text        NOT NULL,
  PRIMARY KEY (build_id, season, episode, event_id, local_id, role),
  FOREIGN KEY (build_id, season, episode, event_id) REFERENCES graph_events (build_id, season, episode, event_id) ON DELETE CASCADE,
  FOREIGN KEY (build_id, season, episode, local_id) REFERENCES graph_characters (build_id, season, episode, local_id)
);

-- One row per relation as the extraction reported it (a change in one episode). Timelines are derived from these rows later.
CREATE TABLE IF NOT EXISTS graph_relations (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  rid             text        NOT NULL,
  a_local_id      text        NOT NULL,
  b_local_id      text        NOT NULL,
  type            text        NOT NULL,
  change          text        NOT NULL,
  detail          text,
  quote           text,
  certainty       text        NOT NULL,
  line_ids        int[]       NOT NULL DEFAULT '{}',
  PRIMARY KEY (build_id, season, episode, rid),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode),
  FOREIGN KEY (build_id, season, episode, a_local_id) REFERENCES graph_characters (build_id, season, episode, local_id),
  FOREIGN KEY (build_id, season, episode, b_local_id) REFERENCES graph_characters (build_id, season, episode, local_id)
);

-- Callbacks: a line that points back to something earlier in the show (free text, event is the local event it belongs to, if any).
CREATE TABLE IF NOT EXISTS graph_refers_back (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  seq             int         NOT NULL,
  event_id        text,
  text            text        NOT NULL,
  line_ids        int[]       NOT NULL DEFAULT '{}',
  PRIMARY KEY (build_id, season, episode, seq),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode),
  FOREIGN KEY (build_id, season, episode, event_id) REFERENCES graph_events (build_id, season, episode, event_id)
);

CREATE TABLE IF NOT EXISTS graph_episode_summaries (
  build_id        int         NOT NULL REFERENCES graph_builds (build_id) ON DELETE CASCADE,
  season          int         NOT NULL,
  episode         int         NOT NULL,
  summary         text        NOT NULL,
  PRIMARY KEY (build_id, season, episode),
  FOREIGN KEY (season, episode) REFERENCES episodes (season, episode)
);
