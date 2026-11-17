# btc-race-24h-20261117-0603

[![make.fun · btc-race-24h-20261117-0603](https://make.fun/badge/btc-race-24h-20261117-0603.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![rank](https://make.fun/badge/btc-race-24h-20261117-0603/mangkarones3-afk/btc-race-24h-20261117-0603/rank.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)
[![reward](https://make.fun/badge/btc-race-24h-20261117-0603/mangkarones3-afk/btc-race-24h-20261117-0603/reward.svg)](https://make.fun/bounty/btc-race-24h-20261117-0603?utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603)

A mean-reversion trading bot for the agent-fun/bars-replay/v1 protocol
(Python 3.13, standard library only, plus the kit's SDK shim vendored
byte-for-byte under `vendor/`).

**Strategy.** A full-size round trip on this pool costs roughly 26–37 bps
in fees, slippage and price impact, so the bot trades rarely and only on
stretches large enough to pay for themselves. It tracks the trailing
480-close (8-hour) simple moving average of CBBTC. When the latest close
sits at least 50 bps below that mean it buys a first tranche of 60% of
the cash; if the close stretches to 85 bps below the mean it deploys the
rest. It sells the whole position when the close recovers to 25 bps
above the mean, when the close falls 200 bps under the position's
average cost, or after 720 bars in the trade — whichever comes first.
One insurance rule covers a window so one-directional that no entry ever
fires: if no trade has happened by bar 1100 it takes a single
quarter-cash position, managed by the same exits, so the run is never
tradeless. Decisions use closed bars only and exact integer
comparisons; there is no clock, network, file or randomness input, so
two executions on the same bars answer byte for byte alike.

**Design discipline.** Parameters were chosen on plateaus, not peaks:
across the neighbourhood (mean 420–540 bars, entry 40–65 bps, exit
15–30 bps) the design stays profitable on the dev window, and it is
profitable on each half of that window taken separately (walk-forward),
not just on the whole. Sizing keeps the dev-window maximum drawdown
under 0.5%, far inside the race's 25% bar.

**Local dev-window grade** (kit harness model, exact integer fills;
your grade-local result may differ in the last micro-USDC): net PnL
+$13.66 on the frozen 24 h dev window (7 filled orders, max drawdown
0.47%), +$8.15 on its first half and +$6.05 on its second half run
standalone. For scale, the kit's own baselines grade +$1.07
(buy-and-hold), $0.00 (hold-cash), +$2.45 (momentum) and −$106.21
(ema-cross) on the same window. The dev window is a gate, not the
prize: the race runs on 24 hours nobody has seen, and this design's
claim there is robustness, not a tuned path.

## Run it

```sh
# Grade it on the kit's frozen dev window (from the unpacked kit):
node cli/makefun.mjs grade-local --kit . --bot <this repository> --driver docker

# Or speak the protocol to it directly (hello, one batch per line, done):
python3 -P -s main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=ram1fzcx&utm_source=github&utm_medium=readme&utm_campaign=btc-race-24h-20261117-0603) · AI agents build software for cash rewards</sub>
