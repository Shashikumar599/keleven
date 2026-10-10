-- Graph views (v3): the query layer over the graph_* tables of migration 013. Views hold no data, so they can be changed or
-- dropped without a rebuild. Every view reads the build named in graph_current.
--
--   graph_characters_now   a person in an episode, with the entity they are linked to and a lower-case name list for lookups
--   graph_relations_now    a relation with both ends resolved: entity name and tier when linked, else the name as extracted
--   graph_events_now       an event with its place name and participants resolved the same way (jsonb list)
--   graph_lines(ids)       the transcript lines behind a list of line ids, in script order

CREATE OR REPLACE VIEW graph_characters_now AS
SELECT c.season, c.episode, c.local_id, c.names, ARRAY(SELECT lower(btrim(n)) FROM unnest(c.names) n) AS names_lc,
       c.description, c.present, c.line_ids, c.entity_name, c.link_tier
FROM graph_characters c JOIN graph_current g USING (build_id);

CREATE OR REPLACE VIEW graph_relations_now AS
SELECT r.season, r.episode, r.rid, r.type, r.change, r.detail, r.quote, r.certainty, r.line_ids,
       a.local_id AS a_local_id, a.names[1] AS a_name, a.entity_name AS a_entity, a.link_tier AS a_tier,
       b.local_id AS b_local_id, b.names[1] AS b_name, b.entity_name AS b_entity, b.link_tier AS b_tier
FROM graph_relations r
JOIN graph_current g USING (build_id)
JOIN graph_characters a ON (a.build_id, a.season, a.episode, a.local_id) = (r.build_id, r.season, r.episode, r.a_local_id)
JOIN graph_characters b ON (b.build_id, b.season, b.episode, b.local_id) = (r.build_id, r.season, r.episode, r.b_local_id);

CREATE OR REPLACE VIEW graph_events_now AS
SELECT e.season, e.episode, e.event_id, e.text, e.kind, e.certainty, e.importance, e.line_ids,
       p.name AS place_name, p.kind AS place_kind,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('local_id', c.local_id, 'name', c.names[1], 'entity', c.entity_name,
                                                      'tier', c.link_tier, 'role', ep.role) ORDER BY ep.role, c.local_id)
                 FROM graph_event_participants ep
                 JOIN graph_characters c ON (c.build_id, c.season, c.episode, c.local_id) = (ep.build_id, ep.season, ep.episode, ep.local_id)
                 WHERE (ep.build_id, ep.season, ep.episode, ep.event_id) = (e.build_id, e.season, e.episode, e.event_id)), '[]'::jsonb) AS participants
FROM graph_events e
JOIN graph_current g USING (build_id)
LEFT JOIN graph_places p ON (p.build_id, p.season, p.episode, p.local_id) = (e.build_id, e.season, e.episode, e.place_local_id);

CREATE OR REPLACE FUNCTION graph_lines(ids int[])
RETURNS TABLE (id int, season int, episode int, scene int, speaker text, text text)
LANGUAGE sql STABLE AS $$
  SELECT l.id, l.season, l.episode, l.scene, l.speaker, l.text FROM lines l WHERE l.id = ANY (ids) ORDER BY l.id
$$;
