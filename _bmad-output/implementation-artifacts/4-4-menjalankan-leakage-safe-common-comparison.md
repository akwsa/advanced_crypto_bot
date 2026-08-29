---
story_id: "4.4"
title: "Menjalankan leakage-safe common comparison"
epic: "4"
status: "done"
baseline_commit: "5c9eeb6"
---

# Story 4.4: Menjalankan leakage-safe common comparison

Status: done

## Story

As a Officer,
I want Champion, Challenger, cash/no-trade, dan executable benchmark dibandingkan dengan method terkunci,
so that backtest terbaik tidak dipilih dari leakage atau benchmark yang diganti.

## Acceptance Criteria

1. **Leakage-Safe Comparison**:
   - Memastikan perbandingan kuantitatif antara Champion, Challenger, dan benchmark terbebas dari *data leakage*.
   - Jika rasio data `UNSCORABLE` > 5%, laporan otomatis ditandai `non-promotable`.
