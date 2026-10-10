-- Relation timelines (v3): turns the per-episode relation rows (begins / ends / revealed) into intervals. A view, so the rules
-- can change without a rebuild. Reads the build named in graph_current, through graph_relations_now.
--
-- A pair is the two ends as entity name (when linked) or lower-case extracted name (when not). boss and crush have a direction
-- (a to b); every other type is symmetric (ends swapped into a fixed order). Rows with certainty joke_or_false are left out.
-- Rows of one pair and type are walked in episode order. begins and revealed put the pair in state "open", ends puts it in
-- "closed". A row starts a new interval when the state before it is closed or empty; otherwise it joins the open interval:
--   begins                     opens an interval (start known); a repeated begins while open is merged into it
--   revealed with nothing open opens an interval with an unknown start (known only from that episode)
--   ends with nothing open     makes an interval with an unknown start and a known end
-- Episodes are ordered as season * 100 + episode. Rows of one episode keep the order of their rid.

CREATE OR REPLACE VIEW graph_timeline_now AS
WITH rows AS (
  SELECT r.type, r.change, r.certainty, r.season, r.episode, r.season * 100 + r.episode AS ep_no,
         NULLIF(regexp_replace(r.rid, '\D', '', 'g'), '')::int AS rid_no, r.rid, r.line_ids, r.detail,
         coalesce(r.a_entity, lower(r.a_name)) AS ka, coalesce(r.b_entity, lower(r.b_name)) AS kb,
         r.a_name, r.b_name, r.a_tier, r.b_tier
  FROM graph_relations_now r
  WHERE r.certainty <> 'joke_or_false'
), ordered AS (
  SELECT type, change, certainty, season, episode, ep_no, rid_no, rid, line_ids, detail,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN ka ELSE kb END AS k1,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN kb ELSE ka END AS k2,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN a_name ELSE b_name END AS name1,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN b_name ELSE a_name END AS name2,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN a_tier ELSE b_tier END AS tier1,
         CASE WHEN type IN ('boss', 'crush') OR ka <= kb THEN b_tier ELSE a_tier END AS tier2
  FROM rows WHERE ka <> kb
), stated AS (
  SELECT *, lag(CASE change WHEN 'ends' THEN 'closed' ELSE 'open' END)
              OVER (PARTITION BY type, k1, k2 ORDER BY ep_no, rid_no) AS prev_state
  FROM ordered
), numbered AS (
  SELECT *, sum(CASE WHEN prev_state IS NULL OR prev_state = 'closed' THEN 1 ELSE 0 END)
              OVER (PARTITION BY type, k1, k2 ORDER BY ep_no, rid_no) AS interval_no
  FROM stated
)
SELECT type, k1 AS a_key, k2 AS b_key, (array_agg(name1 ORDER BY ep_no, rid_no))[1] AS a_name, (array_agg(name2 ORDER BY ep_no, rid_no))[1] AS b_name,
       (array_agg(tier1 ORDER BY ep_no, rid_no))[1] AS a_tier, (array_agg(tier2 ORDER BY ep_no, rid_no))[1] AS b_tier,
       interval_no,
       min(ep_no) FILTER (WHERE change = 'begins')                     AS start_ep,    -- null: start not shown in the data
       min(ep_no) FILTER (WHERE change = 'ends')                       AS end_ep,      -- null: no end shown (still open at the last row)
       min(ep_no)                                                      AS first_ep,
       max(ep_no)                                                      AS last_ep,
       count(DISTINCT ep_no * 1000 + rid_no)                           AS row_count,
       CASE WHEN bool_or(certainty = 'stated') THEN 'stated' ELSE 'implied' END AS certainty,
       array_agg(DISTINCT season || 'x' || episode || ':' || rid)      AS rows_cited,
       array_agg(DISTINCT l ORDER BY l)                                AS line_ids
FROM numbered LEFT JOIN LATERAL unnest(numbered.line_ids) AS l ON true
GROUP BY type, k1, k2, interval_no;
