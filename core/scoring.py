"""Player scoring and ranking logic for FPL Copilot."""


def _avg_fdr_next_n(player_id: int, team_id: int, fixtures: list[dict], n: int = 3) -> float:
    """Calculate average FDR for a player's team over the next N gameweeks.

    Args:
        player_id: The player's element ID (unused directly, kept for context).
        team_id: The player's team ID.
        fixtures: List of upcoming fixture dicts from the FPL API.
        n: Number of upcoming gameweeks to consider.

    Returns:
        Average fixture difficulty rating (1-5 scale).
    """
    team_fixtures = []
    for f in fixtures:
        if f["team_h"] == team_id:
            team_fixtures.append(f["team_h_difficulty"])
        elif f["team_a"] == team_id:
            team_fixtures.append(f["team_a_difficulty"])

    if not team_fixtures:
        return 3.0  # neutral default
    return sum(team_fixtures[:n]) / min(n, len(team_fixtures))


def score_player(player: dict, fixtures: list[dict]) -> float:
    """Score a player using the weighted formula.

    score = (form * 0.3) + (points_per_game * 0.4) + (fixture_score * 0.3)
    where fixture_score = (5 - avg_FDR_next_3_GWs)

    Args:
        player: Player element dict from bootstrap data.
        fixtures: List of upcoming fixture dicts.

    Returns:
        Composite score as a float.
    """
    form = float(player.get("form", 0))
    ppg = float(player.get("points_per_game", 0))
    avg_fdr = _avg_fdr_next_n(player["id"], player["team"], fixtures)
    fixture_score = 5.0 - avg_fdr

    return (form * 0.3) + (ppg * 0.4) + (fixture_score * 0.3)


def rank_players_by_position(
    players: list[dict], position: str, fixtures: list[dict]
) -> list[dict]:
    """Rank players in a given position by composite score.

    Args:
        players: List of player element dicts.
        position: Position to filter by — one of 'GKP', 'DEF', 'MID', 'FWD'
                  or the element_type int (1=GKP, 2=DEF, 3=MID, 4=FWD).
        fixtures: List of upcoming fixture dicts.

    Returns:
        Sorted list of player dicts (highest score first), each augmented
        with a 'composite_score' key.
    """
    position_map = {"GKP": 1, "DEF": 2, "MID": 3, "FWD": 4}
    if isinstance(position, str):
        pos_id = position_map.get(position.upper(), position)
    else:
        pos_id = position

    filtered = [p for p in players if p["element_type"] == pos_id]

    scored = []
    for p in filtered:
        p_copy = dict(p)
        p_copy["composite_score"] = score_player(p, fixtures)
        scored.append(p_copy)

    return sorted(scored, key=lambda x: x["composite_score"], reverse=True)


def calculate_hit_value(
    player_out: dict,
    player_in: dict,
    fixtures: list[dict],
    horizon: int = 3,
) -> dict:
    """Determine whether a transfer hit is worth taking.

    net_gain = expected_points_gain_over_horizon - 4 (hit cost)
    Only flags as worth_it if net_gain > 2.

    Args:
        player_out: Player element dict for the player being sold.
        player_in: Player element dict for the player being bought.
        fixtures: List of upcoming fixture dicts.
        horizon: Number of gameweeks to project over.

    Returns:
        Dict with keys: worth_it (bool), net_gain (float), reasoning (str).
    """
    score_out = score_player(player_out, fixtures) * horizon
    score_in = score_player(player_in, fixtures) * horizon
    expected_gain = score_in - score_out
    hit_cost = 4
    net_gain = expected_gain - hit_cost

    worth_it = net_gain > 2

    reasoning = (
        f"Projected points over {horizon} GWs: "
        f"{player_in['web_name']} = {score_in:.1f}, "
        f"{player_out['web_name']} = {score_out:.1f}. "
        f"Expected gain: {expected_gain:.1f}, minus {hit_cost} hit = net {net_gain:.1f}. "
        f"{'Worth it.' if worth_it else 'Not worth the hit.'}"
    )

    return {
        "worth_it": worth_it,
        "net_gain": round(net_gain, 2),
        "reasoning": reasoning,
    }
