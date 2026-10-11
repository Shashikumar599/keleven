-- graph_events_now gains actor_names: the lower-case names of the participants who are not only witnesses (agent, patient,
-- subject), so a question about two people can ask for events where both took part and skip events where one only watched.
-- Both the extracted name and the linked entity name are listed. Columns are only appended, so existing queries keep working.

CREATE OR REPLACE VIEW graph_events_now AS
SELECT e.season, e.episode, e.event_id, e.text, e.kind, e.certainty, e.importance, e.line_ids,
       p.name AS place_name, p.kind AS place_kind,
       COALESCE((SELECT jsonb_agg(jsonb_build_object('local_id', c.local_id, 'name', c.names[1], 'entity', c.entity_name,
                                                      'tier', c.link_tier, 'role', ep.role) ORDER BY ep.role, c.local_id)
                 FROM graph_event_participants ep
                 JOIN graph_characters c ON (c.build_id, c.season, c.episode, c.local_id) = (ep.build_id, ep.season, ep.episode, ep.local_id)
                 WHERE (ep.build_id, ep.season, ep.episode, ep.event_id) = (e.build_id, e.season, e.episode, e.event_id)), '[]'::jsonb) AS participants,
       COALESCE((SELECT string_agg(DISTINCT lower(n), ' | ')
                 FROM graph_event_participants ep
                 JOIN graph_characters c ON (c.build_id, c.season, c.episode, c.local_id) = (ep.build_id, ep.season, ep.episode, ep.local_id)
                 CROSS JOIN LATERAL unnest(ARRAY[c.names[1], c.entity_name]) AS n
                 WHERE (ep.build_id, ep.season, ep.episode, ep.event_id) = (e.build_id, e.season, e.episode, e.event_id)
                   AND ep.role <> 'witness' AND n IS NOT NULL), '') AS actor_names
FROM graph_events e
JOIN graph_current g USING (build_id)
LEFT JOIN graph_places p ON (p.build_id, p.season, p.episode, p.local_id) = (e.build_id, e.season, e.episode, e.place_local_id);
