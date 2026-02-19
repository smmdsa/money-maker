#!/usr/bin/env python3
"""
Backtest CLI — Herramienta reutilizable para backtesting de estrategias.

Uso:
  python3 backtest_cli.py                          # Scalper 1h BTC 30d (default)
  python3 backtest_cli.py -s scalper -p 30 90 180
  python3 backtest_cli.py -s scalper_1m scalper_5m -c bitcoin -p 7
  python3 backtest_cli.py -s all -c bitcoin ethereum -p 30
  python3 backtest_cli.py --compare                # Todas las estrategias vs BTC 90d
  python3 backtest_cli.py --scalpers               # Todas las variantes scalper vs BTC
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

BASE_URL = "http://localhost:8001"

ALL_STRATEGIES = [
    "scalper", "scalper_1m", "scalper_3m", "scalper_5m", "scalper_15m",
    "trend_rider", "mean_reversion",
    "momentum_sniper", "grid_trader", "confluence_master"
]

ALL_COINS = ["bitcoin", "ethereum", "solana", "ripple", "binancecoin"]

COIN_LABELS = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL",
    "ripple": "XRP", "binancecoin": "BNB", "cardano": "ADA",
    "polkadot": "DOT", "dogecoin": "DOGE",
}

# Reverse map: accept short names like BTC, ETH on the CLI
_SHORT_TO_COIN = {v.lower(): k for k, v in COIN_LABELS.items()}


def _normalize_coin(raw: str) -> str:
    """Accept 'BTC', 'btc', 'bitcoin' → 'bitcoin'."""
    return _SHORT_TO_COIN.get(raw.lower(), raw.lower())

STRATEGY_NAMES = {
    "scalper": "Scalper Pro 1h",
    "scalper_1m": "Scalper Pro 1m",
    "scalper_3m": "Scalper Pro 3m",
    "scalper_5m": "Scalper Pro 5m",
    "scalper_15m": "Scalper Pro 15m",
    "trend_rider": "Trend Rider",
    "mean_reversion": "Mean Reversion",
    "momentum_sniper": "Momentum Sniper",
    "grid_trader": "Grid Trader",
    "confluence_master": "Confluence Master",
}


def run_backtest(strategy: str, coin: str, period: int,
                 leverage: int = 10, balance: float = 100,
                 base_url: str = BASE_URL,
                 trailing_enabled: bool = True) -> dict | None:
    """Ejecuta un backtest y retorna el resultado."""
    payload = json.dumps({
        "strategy": strategy,
        "coin": coin,
        "period_days": period,
        "leverage": leverage,
        "initial_balance": balance,
        "trailing_enabled": trailing_enabled,
    }).encode()

    req = urllib.request.Request(
        f"{base_url}/api/backtest",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
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
    ret_gross = r.get("total_return_gross_pct", ret)
    bh = r.get("buy_hold_return_pct", 0)
    trades = r.get("total_trades", 0)
    wr = r.get("win_rate", 0)
    pf = r.get("profit_factor", 0)
    dd = r.get("max_drawdown_pct", 0)
    sharpe = r.get("sharpe_ratio", 0)
    final = r.get("final_balance", 0)
    final_gross = r.get("final_balance_gross", final)
    commissions = r.get("total_commissions", 0)
    funding = r.get("total_funding", 0)
    total_fees = r.get("total_fees", 0)

    # Calcular R:R desde trades
    wins = [t for t in r.get("trades", []) if (t.get("pnl") or 0) > 0]
    losses = [t for t in r.get("trades", []) if (t.get("pnl") or 0) < 0]
    avg_win = sum((t["pnl"] or 0) for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum((t["pnl"] or 0) for t in losses) / len(losses)) if losses else 1
    rr = avg_win / avg_loss if avg_loss > 0 else 0

    sl_count = len(losses)
    tp_count = len(wins)

    alpha = ret - bh

    # Trailing stop stats
    trail_moves = r.get("trailing_stops_moved", 0)
    trail_closes = r.get("trailing_sl_closes", 0)

    print(f"  ┌─ {name} | {coin_label} | {period}d")
    print(f"  │ Gross:  {format_pct(ret_gross)}  (${final_gross:.2f})")
    print(f"  │ Net:    {format_pct(ret)}  (${final:.2f})  vs B&H: {format_pct(bh)}  Alpha: {format_pct(alpha)}")
    print(f"  │ Fees:   ${total_fees:.2f}  (Comm: ${commissions:.2f} + Funding: ${funding:.2f})")
    print(f"  │ Trades: {trades}  (W:{tp_count} L:{sl_count})")
    print(f"  │ WR: {wr:.1f}%  |  PF: {pf:.2f}  |  R:R: {rr:.2f}  |  Sharpe: {sharpe:.2f}")
    print(f"  │ Max DD: {dd:.1f}%")
    print(f"  │ Trailing: {trail_moves} SL moves, {trail_closes} trailing closes")
    print(f"  └{'─' * 60}")


def print_compare_table(results: list[dict]):
    """Imprime tabla comparativa de múltiples backtests."""
    if not results:
        return

    # Header
    print()
    print(f"  {'Strategy':<20} {'Coin':<6} {'Days':>4}  {'Gross':>8}  {'Net':>8}  "
          f"{'Fees':>6}  {'B&H':>8}  {'Alpha':>8}  {'Trd':>4}  {'WR':>4}  {'PF':>5}  {'DD':>5}  "
          f"{'Trail':>5}  {'TrCl':>4}")
    print(f"  {'─' * 120}")

    for entry in results:
        r = entry["result"]
        s = entry["strategy"]
        c = COIN_LABELS.get(entry["coin"], entry["coin"])
        p = entry["period"]
        name = STRATEGY_NAMES.get(s, s)[:18]

        ret = r.get("total_return_pct", 0)
        ret_gross = r.get("total_return_gross_pct", ret)
        bh = r.get("buy_hold_return_pct", 0)
        alpha = ret - bh
        trades = r.get("total_trades", 0)
        wr = r.get("win_rate", 0)
        pf = r.get("profit_factor", 0)
        dd = r.get("max_drawdown_pct", 0)
        fees = r.get("total_fees", 0)
        trail_moves = r.get("trailing_stops_moved", 0)
        trail_closes = r.get("trailing_sl_closes", 0)

        # Color del return
        ret_s = f"{ret:+.1f}%"
        if ret > 0:
            ret_c = f"\033[92m{ret_s:>8}\033[0m"
        else:
            ret_c = f"\033[91m{ret_s:>8}\033[0m"

        gross_s = f"{ret_gross:+.1f}%"
        if ret_gross > 0:
            gross_c = f"\033[92m{gross_s:>8}\033[0m"
        else:
            gross_c = f"\033[91m{gross_s:>8}\033[0m"

        alpha_s = f"{alpha:+.1f}%"
        if alpha > 0:
            alpha_c = f"\033[92m{alpha_s:>8}\033[0m"
        else:
            alpha_c = f"\033[91m{alpha_s:>8}\033[0m"

        print(f"  {name:<20} {c:<6} {p:>4}  {gross_c}  {ret_c}  "
              f"${fees:>5.1f}  {bh:>+7.1f}%  "
              f"{alpha_c}  {trades:>4}  {wr:>3.0f}%  {pf:>5.2f}  {dd:>4.1f}%  "
              f"{trail_moves:>5}  {trail_closes:>4}")

    print(f"  {'─' * 120}")

    # Resumen
    best = max(results, key=lambda x: x["result"].get("total_return_pct", -999))
    worst = min(results, key=lambda x: x["result"].get("total_return_pct", 999))
    avg_ret = sum(r["result"].get("total_return_pct", 0) for r in results) / len(results)

    # Trailing stats totals
    total_trail_moves = sum(r["result"].get("trailing_stops_moved", 0) for r in results)
    total_trail_closes = sum(r["result"].get("trailing_sl_closes", 0) for r in results)
    total_all_closes = sum(r["result"].get("total_trades", 0) for r in results)
    trail_close_pct = (total_trail_closes / total_all_closes * 100) if total_all_closes > 0 else 0

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
    print(f"     Trailing:  {total_trail_moves} SL moves, {total_trail_closes} trailing closes "
          f"({trail_close_pct:.0f}% de todos los cierres)")


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
    parser.add_argument("--scalpers", action="store_true",
                        help="Comparativa de todos los scalpers vs BTC (max días por TF)")
    parser.add_argument("--url", default=BASE_URL,
                        help=f"URL del servidor (default: {BASE_URL})")
    parser.add_argument("--no-trailing", action="store_true",
                        help="Desactiva trailing stop loss")

    args = parser.parse_args()

    # Resolver 'all'
    base_url = args.url
    trailing_enabled = not args.no_trailing
    strategies = ALL_STRATEGIES if "all" in args.strategies else args.strategies
    coins = ALL_COINS if "all" in [c.lower() for c in args.coins] else [_normalize_coin(c) for c in args.coins]
    periods = args.periods

    # Modo comparativa
    if args.compare:
        strategies = ALL_STRATEGIES
        coins = ["bitcoin"]
        periods = [90]

    # Modo scalpers: cada variante con su periodo máximo natural
    if args.scalpers:
        strategies = ["scalper_1m", "scalper_3m", "scalper_5m", "scalper_15m", "scalper"]
        coins = ["bitcoin"]
        # Override: ejecutar cada scalper con su periodo máximo
        # Se maneja abajo en el loop
        periods = [0]  # sentinel — se reemplaza per-strategy

    # Recalcular total_tests
    if args.scalpers:
        _SCALPER_MAX_DAYS = {
            "scalper_1m": 7, "scalper_3m": 30, "scalper_5m": 30,
            "scalper_15m": 90, "scalper": 90,
        }
        total_tests = sum(len(coins) for s in strategies)
    else:
        total_tests = len(strategies) * len(coins) * len(periods)
    print(f"\n{'═' * 65}")
    print(f"  🚀 BACKTEST CLI")
    print(f"  Estrategias: {', '.join(strategies)}")
    print(f"  Coins:       {', '.join(COIN_LABELS.get(c, c) for c in coins)}")
    print(f"  Periodos:    {', '.join(str(p) + 'd' for p in periods)}")
    print(f"  Leverage:    {args.leverage}x  |  Balance: ${args.balance:.0f}")
    print(f"  Trailing:    {'ON' if trailing_enabled else 'OFF'}")
    print(f"  Total tests: {total_tests}")
    print(f"{'═' * 65}\n")

    # Max days per scalper variant
    _SCALPER_MAX_DAYS = {
        "scalper_1m": 3, "scalper_3m": 14, "scalper_5m": 30,
        "scalper_15m": 30, "scalper": 30,
    }

    all_results = []
    done = 0

    for strategy in strategies:
        for coin in coins:
            effective_periods = periods
            # In --scalpers mode, use each variant's max period
            if args.scalpers and periods == [0]:
                effective_periods = [_SCALPER_MAX_DAYS.get(strategy, 30)]

            for period in effective_periods:
                done += 1
                name = STRATEGY_NAMES.get(strategy, strategy)
                coin_label = COIN_LABELS.get(coin, coin)
                print(f"  [{done}/{total_tests}] {name} | {coin_label} | {period}d ...", end="", flush=True)

                t0 = time.time()
                result = run_backtest(strategy, coin, period, args.leverage, args.balance, base_url, trailing_enabled)
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
