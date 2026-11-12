# NW-003 adversarial review

Status: local implementation and acceptance complete. Both retained 42-slot ledgers and the fresh-browser/download/restart receipts are complete. This is the engineering agent's self-review using `ponytail-review`, source inspection, independent reference checks, real containers and deliberately broken inputs. It is not a second reviewer, a financial professional audit or institutional sign-off.

## What this change does

The main financial workspace now reads and calculates from the approved synthetic data, asks the installed local Qwen profile to investigate and explain the observations, and creates a principal review package. A separate trusted checker compares structured results and linked records with the NW-002 reference. The local operator workflow binds decisions to exact source, policy, package and proposal versions.

The expected load is one local operator and one serialized local inference stream. This is not a multi-user production deployment.

## Findings resolved

1. **An absent record terminated a legitimate investigation.** Development F02-001 asked for the deliberately missing fund component and stopped as a tool failure. The finite source tool now reports available rows and explicit missing IDs. Tool denials return bounded feedback; infrastructure failures remain errors. The failed development run remains on disk; F02-003 later produced a correct needs-source package.

2. **Long duplicated prose used the model time budget without adding evidence.** Development F02-002 timed out. Before the final freeze, the shared prompt was calibrated to a short summary, concise explanations and a small set of model-selected citations; full numeric tables and source bindings remain in the package. Budgets and the model were not expanded or replaced. The exact final prompt and tools are frozen, and final failed slots are retained.

3. **A legitimate local browser request was rejected.** The framework's internal host normalization differed from the browser's origin. The local endpoint now validates the host and forwarded host and compares the origin with the permitted local address, while checking the operator-page token. Real browser acknowledgement/handoff succeeded. Direct boundary checks reject missing tokens, a foreign origin, a foreign host, general command requests and source-path escapes.

4. **A handoff could appear current after a later decision.** Handoff receipts now bind the decision hash as well as the package hash. A new decision requires a new handoff acceptance. Tests cover reject, approve, accept and approve-again sequences.

5. **A retry could collide with files left by an interrupted correction.** Corrections run inside a SQLite transaction and write to a fresh immutable attempt path. If the process stops before commit, the original sources and abandoned files remain; a retry can finish once. Concurrent duplicate requests return the same receipt. A deliberately interrupted correction is tested through retry and restart.

6. **Detected report edits could otherwise allow an old decision to reappear after a revert.** A detected package/action/head binding mismatch is persisted as invalidation, with an audit event. Restoring earlier package bytes does not revive the old decision. This is a local application invariant, not a tamper-proof store against a privileged host operator.

7. **A source or report from history could be mistaken for current work.** The main view distinguishes a running review, a recorded current package and a historical package. Historical views identify the current workspace source/revision and cannot approve an old run. Source replacement clears the active package until a fresh review completes. The old sample is at `/legacy`, and the engineering view returns to the main financial workspace.

8. **A timeout could be misreported as zero model cost.** The frozen summary counts observed responses. The additional `scripts/finance_review_metrics.py` report counts request attempts separately and explicitly labels usage for unanswered requests as unknown. Reported token totals are returned usage only; they are not dollar costs or complete consumption estimates.

9. **A favorable correction could be mistaken for Harness performance.** F01 is a different source snapshot, not an agent improvement or an executed trade. Browser-triggered F05/P02 correction changes the extracted quote from 88 to 80 using the custodian quantity and local market value. Actual container calculations change from needs-source to ready-for-human-review, while reported NAV stays at USD 100 million. The original F05 files stay unchanged. These correction checks are excluded from the paired model denominators.

10. **The verifier rejected legitimate corroboration.** The frozen v1 F05 draft cited the actually read `positions.csv:P02` together with `prices.csv:PX-P02`. A per-finding citation subset falsely rejected that corroboration. The source reader also advertised metadata it could not return. The complete 42-slot ledger, its original grades, and exact frozen sources remain archived; their original scores must not be interpreted as model capability or a causal governance gain. V2 accepts manifest-bound records actually observed across the current calculation or source reads, supports bounded metadata reading, and independently checks read receipts. Regressions retain denials for forged, unread and cross-case records, including unread records with genuine file hashes. Both real F05 development arms passed after the fix. V2 is a separate 42-slot freeze with the same data, model, prompt, tool schemas, budgets and seeds.

## Boundaries tested

- Runtime money arithmetic does not import the reference implementation. The task image contains only the runtime tools and the selected case. It excludes the repository, evaluation answers, credentials and Docker socket.
- Real container checks confirm non-root execution, read-only source files/root filesystem, no external network, capability removal and no host mounts. Unknown approval tools and paths outside the current case are denied.
- Wrong structured numbers, a forged record/hash, altered source bytes, missing source requests and an attempted approval field fail the relevant checks. A stale receipt cannot freshen an old NAV; missing weights remain Unknown; restricted cash and estimated receipts are not committed cash.
- Source changes invalidate old decisions. Stale tabs, duplicate request IDs, approve/source races, interrupted workers, restart readback, rejection and explicit handoff are exercised.
- Ordinary and governed inference share the same model, task, sources, calculator, prompt, budgets and paired seeds. The submission gate is the treatment. Shared confinement is not attributed to the gate alone.
- All 161 protected phase-baseline files remain unchanged at the last preservation check, including all approved inputs and the original financial/NW-001 implementation and records.

## Limits that remain deliberate

- This is a comparison of the submission gate within a shared instrumented runner. It is not a measurement of the whole product versus an entirely unassisted original workflow. Version/approval benefits have separate operational evidence.
- The checker verifies structured figures/states, source-record resolvability, versions and observed calculation receipts. It does not establish the truth or completeness of model prose. A model-selected citation can resolve while being a weak or incomplete explanation of the business claim; full calculation evidence remains attached for principal review. For example, the F02 draft calls the observed 29% equity share out-of-band even though 4% Unknown could fill that gap; its structured state correctly remains needs-source and cannot be signed off. Automated semantic citation faithfulness and professional narrative review are not claimed.
- The structured policy companions are approved inputs. Actual PDF excerpts are read, and other pages are available through the finite reader; this is not a generic arbitrary-IPS extraction benchmark or proof that a human/model reviewed every page.
- Seven known synthetic cases and three repeats per mode do not establish unseen-case reliability. Cache, loading and local workload affect elapsed time. A difference caused by timeout is not evidence that the submission gate improved reasoning.
- A correct needs-source package can be a successful task outcome. An invalid blocked draft or unanswered model request cannot be counted as a successful review.
- Local operator declarations are not authenticated institutional identities. No real principal has signed off these synthetic drafts. Test acknowledgements are explicitly named as test-only and remain in the audit history.
- There is no trade, email, ticketing or other external execution tool. Reviewer time savings, investment outcomes, customer adoption and production suitability remain unmeasured.
- Build and browser checks cover this local checkout. Publication, deployment, portfolio copy and a narrated video are outside the approved phase.

## Verdict

The approved local MVP meets the measured acceptance criteria. Corrected v2 completed 42/42 slots, ordinary and governed each 21/21 with no missing slots or observed forbidden effects; the measured pass-rate gain is zero. Source/version/approval guarantees have separate transactional and browser evidence.

The frozen checker resolves receipts across the saved run. A further candidate-prefix audit independently restricts evidence to each candidate's own hashed trace prefix: all 42 v2 candidates and the fresh browser candidate passed, so a later read did not retroactively justify an earlier citation in these records. See `outputs/nw003/citation-prefix-audit.json`.

Fresh browser run `live-c9189739f6c6` passed independent checks, actual source lookup and PDF download, and recovered the same package/revision/pending decision after restart. All 12 final F00 PDF pages and 12 corrected F02 pages were rendered and visually checked. The final F00 source metadata continues across pages 1–2 without clipping; fixed per-control pagination remains.

All 161 protected files, 1,390 v1 trial files and 1,392 v2 trial files retain their recorded hashes. No real principal approval, professional explanation quality, production outcome or reviewer-time saving is inferred from these results. The final package remains pending human review.
