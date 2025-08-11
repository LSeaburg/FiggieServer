FETCH_AGENT_STATS_SQL = """
    SELECT DISTINCT ON (ea.experiment_id, ea.player_index)
      ea.experiment_id,
      ea.player_index,
      ea.attr_name,
      ea.extra_kwargs,
      ea.polling_rate as normalized_polling_rate,
      ea.attr_name || (ea.player_index + 1) AS agent_name,
      (SELECT COUNT(*) 
       FROM agents a2
       JOIN results r2 ON r2.player_id = a2.player_id
       JOIN rounds rnd ON rnd.round_id = r2.round_id
       WHERE a2.experiment_id = ea.experiment_id
         AND a2.attr_name = ea.attr_name
         AND a2.extra_kwargs::text = ea.extra_kwargs::text
         AND a2.polling_rate = ea.polling_rate * rnd.round_duration / 240.0
      ) as num_games
    FROM experiment_agents AS ea
    WHERE ea.experiment_id = %s
    ORDER BY ea.player_index;
"""

FETCH_EXPERIMENT_STATS_SQL = """
    SELECT 
        e.experiment_id,
        e.name,
        e.description,
        e.created_at,
        COUNT(DISTINCT r.round_id) as total_games,
        COUNT(DISTINCT ea.player_index) as configured_agents
    FROM experiments e
    LEFT JOIN experiment_agents ea ON e.experiment_id = ea.experiment_id
    LEFT JOIN agents a ON ea.experiment_id = a.experiment_id
    LEFT JOIN results r ON a.player_id = r.player_id
    GROUP BY e.experiment_id, e.name, e.description, e.created_at
    ORDER BY e.created_at DESC;
"""

FETCH_INDIVIDUAL_PROFITS_SQL = """
    SELECT
        ea.attr_name || (ea.player_index + 1) AS agent_name,
        ea.attr_name,
        ea.player_index,
        r.final_balance - r.initial_balance AS profit
    FROM experiment_agents AS ea
    JOIN agents AS a ON a.experiment_id = ea.experiment_id 
        AND a.attr_name = ea.attr_name
        AND a.extra_kwargs::text = ea.extra_kwargs::text
    JOIN results AS r ON r.player_id = a.player_id
    JOIN rounds rnd ON rnd.round_id = r.round_id
        AND a.polling_rate = ea.polling_rate * rnd.round_duration / 240.0
    WHERE ea.experiment_id = %s
    ORDER BY ea.player_index, r.round_id;
"""


