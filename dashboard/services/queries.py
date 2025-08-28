FETCH_AGENT_STATS_SQL = """
    SELECT
    ea.experiment_id,
    ea.player_index,
    ea.attr_name,
    ea.extra_kwargs,
    ea.polling_rate AS normalized_polling_rate,
    ea.attr_name || (ea.player_index + 1)::text AS agent_name,
    COUNT(*) FILTER (
        WHERE ABS(a2.polling_rate - (ea.polling_rate * rnd.round_duration / 240.0)) < 0.001
    ) AS num_games,
    AVG((r2.final_balance - r2.initial_balance)) FILTER (
        WHERE ABS(a2.polling_rate - (ea.polling_rate * rnd.round_duration / 240.0)) < 0.001
    ) AS avg_profit
    FROM experiment_agents ea
    LEFT JOIN agents a2
    ON a2.experiment_id = ea.experiment_id
    AND a2.attr_name = ea.attr_name
    AND a2.extra_kwargs::text = ea.extra_kwargs::text
    LEFT JOIN results r2
    ON r2.player_id = a2.player_id
    LEFT JOIN rounds rnd
    ON rnd.round_id = r2.round_id
    WHERE ea.experiment_id = %s
    GROUP BY ea.experiment_id, ea.player_index, ea.attr_name, ea.extra_kwargs, ea.polling_rate
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
        AND ABS(a.polling_rate - (ea.polling_rate * rnd.round_duration / 240.0)) < 0.001
    WHERE ea.experiment_id = %s
    ORDER BY ea.player_index, r.round_id;
"""


