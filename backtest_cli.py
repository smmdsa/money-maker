#!/usr/bin/env python3
"""
Backtest CLI — Herramienta reutilizable para backtesting de estrategias.

Uso:
  python3 backtest_cli.py                          # Scalper BTC 30d (default)
  python3 backtest_cli.py -s scalper -c BTCUSDT -p 30 90 180
  python3 backtest_cli.py -s all -c BTCUSDT ETHUSDT -p 30 90
  python3 backtest_cli.py -s scalper trend_rider -c BTCUSDT -p 30 -b 1000 -l 10
  python3 backtest_cli.py --compare               # Todas las estrategias vs BTC 90d
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8001"

ALL_STRATEGIES = [
    "scalper", "trend_rider", "mean_reversion",
    "momentum_sniper", "grid_trader", "confluence_master"
]

ALL_COINS = ["bitcoin", "ethereum", "solana", "ripple", "binancecoin"]

COIN_LABELS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
    "ripple": "XRP", "binancecoin": "BNB", "cardano": "ADA",
    "polkadot": "DOT", "dogecoin": "DOGE",
}

STRATEGY_NAMES = {
    "scalper": "Scalper Pro",
    "trend_rider": "Trend Rider",
    "mean_reversion": "Mean Reversion",
    "momentum_sniper": "Momentum Sniper",
    "grid_trader": "Grid Trader",
    "confluence_master": "Confluence Master",
}


def run_backtest(strategy: str, coin: str, period: int,
                 leverage: int = 10, balance: float = 100,
                 base_url: str = BASE_URL) -> dict | None:
    """Ejecuta un backtest y retorna el resultado."""
    payload = json.dumps({
        "strategy": strategy,
        "coin": coin,
        "period_days": period,
        "leverage": leverage,
        "initial_balance": balance,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/backtest",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"  ❌ Error de conexión: {e}")
        return None
    except Exception as e:
        print(f"  ❌ Error: {e}")
        return None


def format_pct(val, width=8):
    """Formatea un porcentaje con color ANSI."""
    s = f"{val:+.1f}%"
    if val > 0:
        return f"\033[92m{s:>{width}}\033[0m"  # verde
    elif val < 0:
        return f"\033[91m{s:>{width}}\033[0m"  # rojo
    return f"{s:>{width}}"


def print_result(r: dict, strategy: str, coin: str, period: int):
    """Imprime resultado de un backtest individual."""
    name = STRATEGY_NAMES.get(strategy, strategy)
    coin_label = COIN_LABELS.get(coin, coin)
    ret = r.get("total_return_pct", 0)
    bh = r.get("buy_hold_return_pct", 0)
    trades = r.get("total_trades", 0)
    wr = r.get("win_rate", 0)
    pf = r.get("profit_factor", 0)
    dd = r.get("max_drawdown_pct", 0)
    sharpe = r.get("sharpe_ratio", 0)
    final = r.get("final_balance", 0)

    # Calcular R:R desde trades
    wins = [t for t in r.get("trades", []) if (t.get("pnl") or 0) > 0]
    losses = [t for t in r.get("trades", []) if (t.get("pnl") or 0) < 0]
    avg_win = sum((t["pnl"] or 0) for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum((t["pnl"] or 0) for t in losses) / len(losses)) if losses else 1
    rr = avg_win / avg_loss if avg_loss > 0 else 0

    sl_count = len(losses)
    tp_count = len(wins)

    alpha = ret - bh

    print(f"  ┌─ {name} | {coin_label} | {period}d")
    print(f"  │ Return: {format_pct(ret)}  vs B&H: {format_pct(bh)}  Alpha: {format_pct(alpha)}")
    print(f"  │ Final:  ${final:.2f}  |  Trades: {trades}  (W:{tp_count} L:{sl_count})")
    print(f"  │ WR: {wr:.1f}%  |  PF: {pf:.2f}  |  R:R: {rr:.2f}  |  Sharpe: {sharpe:.2f}")
    print(f"  │ Max DD: {dd:.1f}%")
    print(f"  └{'─' * 60}")


def print_compare_table(results: list[dict]):
    """Imprime tabla comparativa de múltiples backtests."""
    if not results:
        return

    # Header
    print()
    print(f"  {'Strategy':<20} {'Coin':<6} {'Days':>4}  {'Return':>8}  {'B&H':>8}  "
          f"{'Alpha':>8}  {'Trades':>6}  {'WR':>5}  {'PF':>5}  {'R:R':>5}  {'DD':>6}")
    print(f"  {'─' * 100}")

    for entry in results:
        r = entry["result"]
        s = entry["strategy"]
        c = COIN_LABELS.get(entry["coin"], entry["coin"])
        p = entry["period"]
        name = STRATEGY_NAMES.get(s, s)[:18]

        ret = r.get("total_return_pct", 0)
        bh = r.get("buy_hold_return_pct", 0)
        alpha = ret - bh
        trades = r.get("total_trades", 0)
        wr = r.get("win_rate", 0)
        pf = r.get("profit_factor", 0)
        dd = r.get("max_drawdown_pct", 0)

        wins = [t for t in r.get("trades", []) if (t.get("pnl") or 0) > 0]
        losses = [t for t in r.get("trades", []) if (t.get("pnl") or 0) < 0]
        avg_win = sum((t["pnl"] or 0) for t in wins) / len(wins) if wins else 0
        avg_loss = abs(sum((t["pnl"] or 0) for t in losses) / len(losses)) if losses else 1
        rr = avg_win / avg_loss if avg_loss > 0 else 0

        # Color del return
        ret_s = f"{ret:+.1f}%"
        if ret > 0:
            ret_c = f"\033[92m{ret_s:>8}\033[0m"
        else:
            ret_c = f"\033[91m{ret_s:>8}\033[0m"

        alpha_s = f"{alpha:+.1f}%"
        if alpha > 0:
            alpha_c = f"\033[92m{alpha_s:>8}\033[0m"
        else:
            alpha_c = f"\033[91m{alpha_s:>8}\033[0m"

        print(f"  {name:<20} {c:<6} {p:>4}  {ret_c}  {bh:>+7.1f}%  "
              f"{alpha_c}  {trades:>6}  {wr:>4.0f}%  {pf:>5.2f}  {rr:>5.2f}  {dd:>5.1f}%")

    print(f"  {'─' * 100}")

    # Resumen
    best = max(results, key=lambda x: x["result"].get("total_return_pct", -999))
    worst = min(results, key=lambda x: x["result"].get("total_return_pct", 999))
    avg_ret = sum(r["result"].get("total_return_pct", 0) for r in results) / len(results)

    print(f"\n  📊 Resumen:")
    best_cl = COIN_LABELS.get(best['coin'], best['coin'])
    worst_cl = COIN_LABELS.get(worst['coin'], worst['coin'])
    print(f"     Mejor:    {STRATEGY_NAMES.get(best['strategy'], best['strategy'])} "
          f"({best_cl} {best['period']}d) → {format_pct(best['result']['total_return_pct'])}")
    print(f"     Peor:     {STRATEGY_NAMES.get(worst['strategy'], worst['strategy'])} "
          f"({worst_cl} {worst['period']}d) → {format_pct(worst['result']['total_return_pct'])}")
    print(f"     Promedio: {format_pct(avg_ret)}")
    profitable = sum(1 for r in results if r["result"].get("total_return_pct", 0) > 0)
    print(f"     Rentables: {profitable}/{len(results)} ({profitable/len(results)*100:.0f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="🚀 Backtest CLI — Test de estrategias de trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  %(prog)s                                    # Default: Scalper BTC 30d
  %(prog)s -s scalper -p 30 90 180            # Scalper en 3 periodos
  %(prog)s -s scalper -c bitcoin ethereum     # Scalper en BTC y ETH
  %(prog)s -s all -p 90                       # Todas las estrategias 90d
  %(prog)s --compare                          # Comparativa completa
  %(prog)s -s scalper -c all -p 30            # Scalper en todas las coins
  %(prog)s -b 1000 -l 5                       # Balance $1000, leverage 5x
        """,
    )
    parser.add_argument("-s", "--strategies", nargs="+", default=["scalper"],
                        help="Estrategias a testear (o 'all')")
    parser.add_argument("-c", "--coins", nargs="+", default=["bitcoin"],
                        help="Coins: bitcoin, ethereum, solana, ripple, binancecoin (o 'all')")
    parser.add_argument("-p", "--periods", nargs="+", type=int, default=[30],
                        help="Periodos en días (ej: 30 90 180)")
    parser.add_argument("-l", "--leverage", type=int, default=10,
                        help="Leverage (default: 10)")
    parser.add_argument("-b", "--balance", type=float, default=100,
                        help="Balance inicial (default: 100)")
    parser.add_argument("--compare", action="store_true",
                        help="Comparativa completa: todas las estrategias vs BTC 90d")
    parser.add_argument("--url", default=BASE_URL,
                        help=f"URL del servidor (default: {BASE_URL})")

    args = parser.parse_args()

    # Resolver 'all'
    base_url = args.url
    strategies = ALL_STRATEGIES if "all" in args.strategies else args.strategies
    coins = ALL_COINS if "all" in args.coins else args.coins
    periods = args.periods

    # Modo comparativa
    if args.compare:
        strategies = ALL_STRATEGIES
        coins = ["bitcoin"]
        periods = [90]

    total_tests = len(strategies) * len(coins) * len(periods)
    print(f"\n{'═' * 65}")
    print(f"  🚀 BACKTEST CLI")
    print(f"  Estrategias: {', '.join(strategies)}")
    print(f"  Coins:       {', '.join(COIN_LABELS.get(c, c) for c in coins)}")
    print(f"  Periodos:    {', '.join(str(p) + 'd' for p in periods)}")
    print(f"  Leverage:    {args.leverage}x  |  Balance: ${args.balance:.0f}")
    print(f"  Total tests: {total_tests}")
    print(f"{'═' * 65}\n")

    all_results = []
    done = 0

    for strategy in strategies:
        for coin in coins:
            for period in periods:
                done += 1
                name = STRATEGY_NAMES.get(strategy, strategy)
                coin_label = COIN_LABELS.get(coin, coin)
                print(f"  [{done}/{total_tests}] {name} | {coin_label} | {period}d ...", end="", flush=True)

                t0 = time.time()
                result = run_backtest(strategy, coin, period, args.leverage, args.balance, base_url)
                elapsed = time.time() - t0

                if result:
                    ret = result.get("total_return_pct", 0)
                    trades = result.get("total_trades", 0)
                    print(f" {format_pct(ret)}  ({trades} trades, {elapsed:.1f}s)")
                    all_results.append({
                        "strategy": strategy,
                        "coin": coin,
                        "period": period,
                        "result": result,
                    })
                else:
                    print(f" ❌ FAILED ({elapsed:.1f}s)")

    # Mostrar resultados detallados o tabla comparativa
    print()
    if total_tests == 1 and all_results:
        print_result(all_results[0]["result"], strategies[0], coins[0], periods[0])
    elif all_results:
        print_compare_table(all_results)

    print()


if __name__ == "__main__":
    main()
