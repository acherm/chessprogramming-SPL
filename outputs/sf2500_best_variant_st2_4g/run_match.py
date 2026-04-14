from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import chess
import chess.engine
import chess.pgn

REPO = Path('/Users/mathieuacher/SANDBOX/chessprogramming-vm')
OUT_DIR = REPO / 'outputs' / 'sf2500_best_variant_st2_4g'
VARIANT_BIN = REPO / 'outputs' / 'sf2500_realistic_best_variant' / 'variant_bin' / 'phase3_full_eval'
STOCKFISH_BIN = Path('/opt/homebrew/bin/stockfish')
OPENINGS_PGN = REPO / 'outputs' / 'proper_elo_tournament_strong_v1' / 'openings.pgn'
OPENING_PLIES = 8
OPENING_COUNT = 2
MOVE_TIME_SEC = 2.0
MAX_FULLMOVES = 80
VARIANT_NAME = 'phase3_full_eval'
STOCKFISH_NAME = 'stockfish_2500'
STOCKFISH_OPTIONS = {
    'Skill Level': 20,
    'UCI_LimitStrength': True,
    'UCI_Elo': 2500,
    'Threads': 1,
    'Hash': 64,
}


def load_openings() -> list[dict[str, str]]:
    openings: list[dict[str, str]] = []
    with OPENINGS_PGN.open() as handle:
        while len(openings) < OPENING_COUNT:
            game = chess.pgn.read_game(handle)
            if game is None:
                break
            board = game.board()
            opening_moves: list[str] = []
            for idx, move in enumerate(game.mainline_moves()):
                if idx >= OPENING_PLIES:
                    break
                opening_moves.append(move.uci())
                board.push(move)
            openings.append(
                {
                    'opening_index': str(len(openings) + 1),
                    'source_event': game.headers.get('Event', f'opening_{len(openings)+1}'),
                    'source_site': game.headers.get('Site', ''),
                    'fen': board.fen(),
                    'opening_moves_uci': ' '.join(opening_moves),
                }
            )
    if len(openings) < OPENING_COUNT:
        raise RuntimeError(f'needed {OPENING_COUNT} openings, found {len(openings)}')
    return openings


def engine_for(role: str, variant: chess.engine.SimpleEngine, stockfish: chess.engine.SimpleEngine) -> chess.engine.SimpleEngine:
    return variant if role == 'variant' else stockfish


def role_to_name(role: str) -> str:
    return VARIANT_NAME if role == 'variant' else STOCKFISH_NAME


def result_for_winner(winner_role: str | None) -> str:
    if winner_role is None:
        return '1/2-1/2'
    return '1-0' if winner_role == 'white' else '0-1'


def run_game(spec: dict[str, str], game_no: int) -> tuple[dict[str, object], chess.pgn.Game]:
    variant = chess.engine.SimpleEngine.popen_uci(str(VARIANT_BIN))
    stockfish = chess.engine.SimpleEngine.popen_uci(str(STOCKFISH_BIN))
    stockfish.configure(STOCKFISH_OPTIONS)
    board = chess.Board(spec['fen'])
    game = chess.pgn.Game()
    game.headers['Event'] = 'Best SPL Variant vs Stockfish 2500'
    game.headers['Site'] = 'local-uci'
    game.headers['Round'] = str(game_no)
    game.headers['White'] = role_to_name(spec['white_role'])
    game.headers['Black'] = role_to_name(spec['black_role'])
    game.headers['SetUp'] = '1'
    game.headers['FEN'] = spec['fen']
    game.headers['OpeningIndex'] = spec['opening_index']
    game.headers['OpeningMoves'] = spec['opening_moves_uci']
    game.headers['MoveTimeMs'] = str(int(MOVE_TIME_SEC * 1000))
    node = game

    variant_depths: list[int] = []
    stockfish_depths: list[int] = []
    termination = 'normal'
    winner_role: str | None = None
    illegal = False
    start = time.time()

    try:
        for _ in range(MAX_FULLMOVES * 2):
            turn_role = spec['white_role'] if board.turn == chess.WHITE else spec['black_role']
            engine = engine_for(turn_role, variant, stockfish)
            try:
                play_result = engine.play(
                    board,
                    chess.engine.Limit(time=MOVE_TIME_SEC),
                    info=chess.engine.INFO_ALL,
                )
            except Exception as exc:
                termination = f'engine_exception:{turn_role}:{type(exc).__name__}'
                winner_role = 'black' if board.turn == chess.WHITE else 'white'
                break

            move = play_result.move
            if move is None or move not in board.legal_moves:
                termination = f'illegal_move:{turn_role}'
                illegal = True
                winner_role = 'black' if board.turn == chess.WHITE else 'white'
                break

            depth = play_result.info.get('depth')
            if isinstance(depth, int):
                if turn_role == 'variant':
                    variant_depths.append(depth)
                else:
                    stockfish_depths.append(depth)

            node = node.add_variation(move)
            board.push(move)

            outcome = board.outcome(claim_draw=True)
            if outcome is not None:
                termination = outcome.termination.name.lower()
                if outcome.winner is None:
                    winner_role = None
                else:
                    winner_role = 'white' if outcome.winner else 'black'
                break
        else:
            termination = 'move_cap'
            winner_role = None
    finally:
        variant.quit()
        stockfish.quit()

    result = result_for_winner(winner_role)
    game.headers['Result'] = result
    game.headers['Termination'] = termination
    elapsed = round(time.time() - start, 3)

    variant_score = 0.5 if result == '1/2-1/2' else 0.0
    if result == '1-0' and spec['white_role'] == 'variant':
        variant_score = 1.0
    elif result == '0-1' and spec['black_role'] == 'variant':
        variant_score = 1.0

    row: dict[str, object] = {
        'game': game_no,
        'opening_index': spec['opening_index'],
        'white': role_to_name(spec['white_role']),
        'black': role_to_name(spec['black_role']),
        'result': result,
        'termination': termination,
        'variant_score': variant_score,
        'variant_color': 'white' if spec['white_role'] == 'variant' else 'black',
        'illegal': illegal,
        'elapsed_sec': elapsed,
        'variant_avg_depth': round(sum(variant_depths) / len(variant_depths), 2) if variant_depths else 0.0,
        'variant_max_depth': max(variant_depths) if variant_depths else 0,
        'stockfish_avg_depth': round(sum(stockfish_depths) / len(stockfish_depths), 2) if stockfish_depths else 0.0,
        'stockfish_max_depth': max(stockfish_depths) if stockfish_depths else 0,
        'ply_count': board.ply(),
    }
    return row, game


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    openings = load_openings()
    schedule: list[dict[str, str]] = []
    for opening in openings:
        schedule.append(opening | {'white_role': 'variant', 'black_role': 'stockfish'})
        schedule.append(opening | {'white_role': 'stockfish', 'black_role': 'variant'})

    rows: list[dict[str, object]] = []
    games: list[chess.pgn.Game] = []
    started = time.time()
    for idx, spec in enumerate(schedule, start=1):
        row, game = run_game(spec, idx)
        rows.append(row)
        games.append(game)
        print(json.dumps(row), flush=True)

    with (OUT_DIR / 'games.pgn').open('w', encoding='utf-8') as handle:
        for game in games:
            print(game, file=handle, end='\n\n')

    with (OUT_DIR / 'games.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    score = sum(float(row['variant_score']) for row in rows)
    wins = sum(1 for row in rows if float(row['variant_score']) == 1.0)
    draws = sum(1 for row in rows if float(row['variant_score']) == 0.5)
    losses = len(rows) - wins - draws
    white_games = sum(1 for row in rows if row['variant_color'] == 'white')
    white_wins = sum(1 for row in rows if row['variant_color'] == 'white' and float(row['variant_score']) == 1.0)
    black_games = sum(1 for row in rows if row['variant_color'] == 'black')
    black_wins = sum(1 for row in rows if row['variant_color'] == 'black' and float(row['variant_score']) == 1.0)
    illegal_count = sum(1 for row in rows if bool(row['illegal']))
    move_cap_draws = sum(1 for row in rows if row['termination'] == 'move_cap')
    variant_depths = [float(row['variant_avg_depth']) for row in rows if float(row['variant_avg_depth']) > 0]
    variant_max_depth = max(int(row['variant_max_depth']) for row in rows)
    stockfish_depths = [float(row['stockfish_avg_depth']) for row in rows if float(row['stockfish_avg_depth']) > 0]
    stockfish_max_depth = max(int(row['stockfish_max_depth']) for row in rows)
    total_elapsed = round(time.time() - started, 3)

    summary = {
        'variant': VARIANT_NAME,
        'opponent': STOCKFISH_NAME,
        'setup': {
            'runner': 'python-chess UCI referee',
            'movetime_ms': int(MOVE_TIME_SEC * 1000),
            'opening_plies': OPENING_PLIES,
            'opening_count': OPENING_COUNT,
            'games': len(rows),
            'max_fullmoves': MAX_FULLMOVES,
            'stockfish_options': STOCKFISH_OPTIONS,
        },
        'result': {
            'wins': wins,
            'losses': losses,
            'draws': draws,
            'score': score,
            'games': len(rows),
            'score_pct': round(100.0 * score / len(rows), 1),
            'white_games': white_games,
            'white_wins': white_wins,
            'black_games': black_games,
            'black_wins': black_wins,
            'illegal_count': illegal_count,
            'move_cap_draws': move_cap_draws,
        },
        'depth': {
            'variant_avg_depth_across_games': round(sum(variant_depths) / len(variant_depths), 2) if variant_depths else 0.0,
            'variant_max_depth_seen': variant_max_depth,
            'stockfish_avg_depth_across_games': round(sum(stockfish_depths) / len(stockfish_depths), 2) if stockfish_depths else 0.0,
            'stockfish_max_depth_seen': stockfish_max_depth,
        },
        'timing': {
            'total_elapsed_sec': total_elapsed,
            'avg_game_sec': round(total_elapsed / len(rows), 2),
        },
    }

    (OUT_DIR / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    with (OUT_DIR / 'summary.csv').open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['variant','games','wins','losses','draws','score','score_pct','white_wins','black_wins','illegal_count','move_cap_draws','variant_avg_depth_across_games','variant_max_depth_seen','stockfish_avg_depth_across_games','stockfish_max_depth_seen','total_elapsed_sec'])
        writer.writeheader()
        writer.writerow({
            'variant': VARIANT_NAME,
            'games': len(rows),
            'wins': wins,
            'losses': losses,
            'draws': draws,
            'score': score,
            'score_pct': round(100.0 * score / len(rows), 1),
            'white_wins': white_wins,
            'black_wins': black_wins,
            'illegal_count': illegal_count,
            'move_cap_draws': move_cap_draws,
            'variant_avg_depth_across_games': summary['depth']['variant_avg_depth_across_games'],
            'variant_max_depth_seen': variant_max_depth,
            'stockfish_avg_depth_across_games': summary['depth']['stockfish_avg_depth_across_games'],
            'stockfish_max_depth_seen': stockfish_max_depth,
            'total_elapsed_sec': total_elapsed,
        })

    report = f"""# Best Variant vs Stockfish 2500

## Setup
- Variant: `{VARIANT_NAME}`
- Opponent: `{STOCKFISH_NAME}`
- Referee: `python-chess` UCI controller
- Move time: `{int(MOVE_TIME_SEC * 1000)} ms` per move
- Openings: `{OPENING_COUNT}` opening seeds from `outputs/proper_elo_tournament_strong_v1/openings.pgn`, each with color swap
- Max fullmoves per game: `{MAX_FULLMOVES}`

## Result
- Score: `{score}/{len(rows)}` ({round(100.0 * score / len(rows), 1)}%)
- Record: `{wins}W {draws}D {losses}L`
- White wins: `{white_wins}/{white_games}`
- Black wins: `{black_wins}/{black_games}`
- Illegal moves: `{illegal_count}`
- Move-cap draws: `{move_cap_draws}`

## Depth
- Variant average depth across games: `{summary['depth']['variant_avg_depth_across_games']}`
- Variant max depth seen: `{variant_max_depth}`
- Stockfish average depth across games: `{summary['depth']['stockfish_avg_depth_across_games']}`
- Stockfish max depth seen: `{stockfish_max_depth}`

## Files
- `games.pgn`
- `games.csv`
- `summary.csv`
- `summary.json`
"""
    (OUT_DIR / 'report.md').write_text(report, encoding='utf-8')


if __name__ == '__main__':
    main()
