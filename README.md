# backtest-verification-kit

**How I check that a backtest is telling the truth** — distilled from running a live, fully automated
multi-strategy, multi-asset portfolio (crypto, gold, silver, equity indices).

This repository is about *verification*, not about an edge. The example strategy is a textbook
Donchian breakout on public Binance data; my live strategies, parameters and accounts are not here.

```
public data ──► canonical run() ──► random-entry null ──► EV by window ──► live vs backtest
 (verify/data)   (verify/backtest)     (verify/null)        (verify/ev)     (verify/exec_quality)
                        ▲
                 verify/spec.py  (the only place constants live)
```

## What is in here

| Piece | Why it exists |
|---|---|
| `verify/spec.py` | Every constant in one file, plus `KNOWN_OPTIMISM` — the biases not yet corrected, quoted with every number. |
| `verify/backtest.py` | One simulator. Bar-order rules: signal on close → fill next bar; **fill before stop inside a bar**; gap stops fill at the open; fixed same-day order. |
| `verify/null.py` | Random-entry null that shares every rule except *when* to enter. Gates are percentiles against it. |
| `verify/ev.py` | Expected wealth over 3 years (20-day block bootstrap), per window, and with the best day removed. |
| `verify/exec_quality.py` | Live cost vs the backtest assumption — with the reference-price rules that once turned an 8bp cost into a fake 15bp. |
| `docs/INCIDENTS.md` | **Eleven measurement bugs** that made results look better than they were, how big each error was, and the rule that now prevents it. |
| `docs/PREREG_TEMPLATE.md` | Criteria are fixed before measuring; every attempt is counted. |
| `tests/` | Each test locks a rule whose violation once inflated a real result. |

## Run it

```bash
pip install -r requirements.txt
python -m pytest -q                 # offline, synthetic data
python -m examples.run_example      # downloads public daily bars (no API key)
```

Example output (in-sample, includes the 2020–21 bull market — not a performance claim):

```
CAGR 28.4% | MDD -14.4% | trades 304
Random-entry null: actual +6.64%/trade vs null +1.87 +/- 0.99 -> 100.0 percentile
3-year EV: all 2.26x | 2024+ 1.63x | 2025+ 1.17x  (best day removed: 2.13 / 1.52 / 1.04)
```

Read it the way the kit intends: the signal beats random entry with the same rules, but the edge shrinks
sharply in recent windows, and the 2025+ result mostly depends on a few days. That is the kind of
sentence a verification step should produce.

## The live system this comes from (not included)

* Several strategies across crypto perpetuals and gold/index markets, running unattended on two servers that watch each other.
* Daily live-vs-backtest parity check: every skipped signal must carry a reason the backtest knows.
* Weekly execution-cost and implementation-shortfall reports (live round trip 8.0bp vs 11bp assumed).
* A research ledger of 70+ rejected strategy families, a pre-registration budget, and a research moratorium when results started driving too many changes.

---

## 한국어 요약

**백테스트가 진짜인지 검증하는 방법**을, 크립토·금·은·주가지수에 걸친 멀티에셋 자동매매 포트폴리오를 실제로 운영하며 정리한 저장소입니다.
전략 자체(엣지)가 아니라 **검증 절차**가 주제입니다. 예시 전략은 교과서식 돈치안 돌파이고, 실제 운용 전략·파라미터·계좌는 포함하지 않습니다.

- **하나의 정본 시뮬레이터**: 설정은 `spec.py` 한 곳, 변형은 `run()` 인자로만.
- **봉 안 순서 규칙**: 체결이 먼저, 손절이 나중. 갭 손절은 시가 체결.
- **무작위 진입 귀무**: 진입 시점만 무작위로 바꾸고 나머지 규칙은 같게 해서 백분위로 판정.
- **기대 자산(EV)**: 세 구간 + 최고의 하루 제외.
- **실행비용 실측**: 손절은 트리거 가격 기준으로 슬리피지 측정.
- **사고 기록 11건** (`docs/INCIDENTS.md`): 결과를 부풀린 측정 버그와 오차 크기, 재발 방지 규칙.

License: MIT
