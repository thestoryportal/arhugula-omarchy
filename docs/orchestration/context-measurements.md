# Context measurements for the optimization rollout

These are local transcript observations from September 22–23, 2026, not model
capacity or subscription-cost measurements. The CLI's input count includes cached
input once. The role policy and launch changes were introduced during this run,
so the sessions below are not a controlled A/B test.

| Session | Observation |
| --- | --- |
| Buford `01a0cc21` | First reported request used 15,237 of a displayed 258,400-token denominator (5.9%). This does not explain the user's separate ~38% UI observation. |
| Prior Opus reviewer `b8550e64` | Native compaction boundary recorded 63,828 pre / 22,490 post tokens, lasting about 103 seconds. Its one-off launch script specified `--autocompact 100k`. |
| Runtime Sonnet `9d04caf9` | Native compaction boundary recorded 67,217 pre / 14,576 post tokens, lasting about 212 seconds. Its one-off launch script also specified `--autocompact 100k`. |
| Fresh Sonnet reviewer `377d0a88` | Initial two response inputs were 11,307 and 14,148. The completed policy source review reached 89,740 before any compaction; the reviewer then released and was refreshed in the same window. This pass included full Laws:Code and Laws:Prompt/craft reads. |

The observed compaction boundaries do not prove a model context limit or that the
100k launch setting caused compaction at those counts. The fresh reviewer still
spent substantial context on required Laws and task material. Role-scoped loading
removes unrelated startup reads; it cannot erase the full-read requirement when a
review actually covers code and instructions. Use `session_context inspect` on
each current transcript and admit only work that fits its measured budget. Review
quality and long-run cost should be assessed over later completed assignments.

The installed user monitor initially emitted retained historical metadata events,
then coalesced unchanged scans. With `repair_paused: true`, it had zero pending and
zero sent queue notifications during initial verification. It never calls a model.
