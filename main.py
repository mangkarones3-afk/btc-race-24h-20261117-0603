"""Mean-reversion bot for agent-fun/bars-replay/v1 (make.fun btc-race-24h).

Strategy, in one paragraph: on a near-flat, fee-heavy window the only moves
worth paying for are the larger ones. A full-size round trip costs roughly
26-37 bps in fees, slippage and pool impact, so this bot trades rarely and
only when the price has actually stretched: it buys CBBTC when the latest
close sits at least ENTRY_BPS below its trailing MEAN_BARS simple moving
average, in two tranches — a first share of the cash at the entry stretch
and the rest if the close stretches a further ADD_BPS below the mean — and
sells the whole position once the close recovers to EXIT_BPS above that
average. A stop LOSS_BPS under the position's average cost and a
MAX_HOLD_BARS time stop bound the trade. Everything is decided on closed
bars only; orders fill at the next bar's open, as the protocol says.

One insurance rule guards the race's at-least-one-trade bar: if no trade
has happened by LATE_BAR — a window so one-directional that the close
never stretched below the mean — the bot takes one small position (a
quarter of the cash) and manages it with the same exits, so it is never
left holding nothing but untraded cash. It cannot fire in a window that
offered a real entry, and it never grows into the second tranche.

Determinism: no clock, no network, no files, no randomness at all. The
moving-average tests are exact integer comparisons, so two executions on
the same bars produce byte-identical replies.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))
import makefun_bars

SYMBOL = "CBBTC"

# --- strategy parameters (see the design notes in README.md) ----------------
MEAN_BARS = 480        # trailing closes in the mean (8 hours of minutes)
ENTRY_BPS = 50         # first tranche when close <= mean * (1 - 50 bps)
ADD_BPS = 85           # second tranche when close <= mean * (1 - 85 bps)
FIRST_NUM = 3          # the first tranche is FIRST_NUM/FIRST_DEN of the cash
FIRST_DEN = 5
EXIT_BPS = 25          # sell when close >= mean * (1 + 25 bps)
STOP_BPS = 200         # sell when close <= average cost * (1 - 200 bps)
MAX_HOLD_BARS = 720    # sell once the position is this many bars old
LATE_BAR = 1100        # insurance: if still tradeless here, take a small position
LATE_NUM = 1           # the insurance position is LATE_NUM/LATE_DEN of the cash
LATE_DEN = 4
MAX_SLIPPAGE_BPS = 300 # reject a fill further than this from the last close

BPS = 10_000


class MeanReversion:
    """The strategy state: the close history and one open position at most."""

    def __init__(self):
        self.closes = []          # every CBBTC close so far, raw price units
        self.entry_seq = None     # batch seq whose account first showed the position
        self.pending = None       # "buy" or "sell": an order decided last batch
        self.added = False        # the second tranche is in
        self.ever_traded = False  # a position has been held at some point
        self.late = False         # the open position is the insurance one

    # -- helpers -------------------------------------------------------------
    def mean_test(self, close, bps, below):
        """True when `close` is at least `bps` below (or above) the trailing mean.

        Exact integer form of close <= mean * (1 - bps/10000): with total the
        sum of the last MEAN_BARS closes, close * MEAN_BARS * 10000 is compared
        against total * (10000 - bps), so no float ever enters the decision.
        """
        if len(self.closes) < MEAN_BARS:
            return False
        total = sum(self.closes[-MEAN_BARS:])
        lhs = close * MEAN_BARS * BPS
        if below:
            return lhs <= total * (BPS - bps)
        return lhs >= total * (BPS + bps)

    def average_cost(self, state):
        """The open position's average cost per whole CBBTC, in USDC (float).

        The account reports cost in quote units (fees included) and quantity
        at the symbol's qty scale; their ratio is the effective price paid.
        Used only for the stop test, never for sizing.
        """
        held = state.positions.get(SYMBOL)
        if held is None or held.qty == 0:
            return None
        quote_scale = state.hello["capital"]["quote_scale"]
        qty_scale = state.symbols[SYMBOL]["qty_scale"]
        return (held.cost / 10**quote_scale) / (held.qty / 10**qty_scale)

    # -- the per-batch decision ----------------------------------------------
    def decide(self, state, batch):
        # Record this batch's close, if the minute carried a CBBTC bar.
        for bar in batch["bars"]:
            if bar["symbol"] == SYMBOL:
                self.closes.append(int(bar["c"]))
        if state.warming_up or not self.closes:
            return None
        # An order decided on the previous batch has now been answered by the
        # account in this one; the pending flag only lives across one batch.
        self.pending = None

        close = self.closes[-1]
        held = state.positions.get(SYMBOL)
        price_scale = state.symbols[SYMBOL]["price_scale"]
        close_usdc = close / 10**price_scale

        if held is not None and held.qty > 0:
            self.ever_traded = True
            if self.entry_seq is None:
                self.entry_seq = state.seq
            # Exit 1: the stretch has reverted past the mean.
            if self.mean_test(close, EXIT_BPS, below=False):
                return self._sell(state)
            # Exit 2: the trade is wrong by more than the stop.
            avg = self.average_cost(state)
            if avg is not None and close_usdc <= avg * (1 - STOP_BPS / BPS):
                return self._sell(state)
            # Exit 3: the trade has had its time.
            if state.seq - self.entry_seq >= MAX_HOLD_BARS:
                return self._sell(state)
            # No exit: if the stretch deepens, complete the position with
            # the cash that is left. One add only, at the deeper band, and
            # never on the insurance position.
            if not self.added and not self.late and state.cash >= 1_000_000 and \
                    self.mean_test(close, ADD_BPS, below=True):
                self.added = True
                self.pending = "buy"
                return [{
                    "side": "buy",
                    "symbol": SYMBOL,
                    "notional_quote_units": state.cash,
                    "max_slippage_bps": MAX_SLIPPAGE_BPS,
                }]
            return None

        self.entry_seq = None
        self.added = False
        # Entry: the close has stretched far enough below the mean to pay
        # the round trip and still leave edge. First tranche only; the add
        # above decides whether the rest follows.
        if state.cash >= 1_000_000 and self.mean_test(close, ENTRY_BPS, below=True):
            self.late = False
            self.pending = "buy"
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash * FIRST_NUM // FIRST_DEN,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        # Insurance: no real entry ever appeared and the window is nearly
        # over. Take the small position so the run is not tradeless; the
        # ordinary exits above manage it from here.
        if not self.ever_traded and state.seq >= LATE_BAR and state.cash >= 1_000_000:
            self.late = True
            self.pending = "buy"
            return [{
                "side": "buy",
                "symbol": SYMBOL,
                "notional_quote_units": state.cash * LATE_NUM // LATE_DEN,
                "max_slippage_bps": MAX_SLIPPAGE_BPS,
            }]
        return None

    def _sell(self, state):
        held = state.positions[SYMBOL]
        self.pending = "sell"
        return [{
            "side": "sell",
            "symbol": SYMBOL,
            "qty": held.qty,
            "max_slippage_bps": MAX_SLIPPAGE_BPS,
        }]


BOT = MeanReversion()


def on_batch(state, batch):
    return BOT.decide(state, batch)


if __name__ == "__main__":
    makefun_bars.run(on_batch)
