SELECT
    descendant_version_id,
    version_id,
    parent_version_id,
    depth,
    cycle_detected
FROM prompt_version_lineage
WHERE descendant_version_id = :'version_id'::uuid
ORDER BY depth;
