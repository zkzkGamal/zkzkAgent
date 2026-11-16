# zkzkAgent: Nosana dropping out mid-task — 2026-11-16-dropout

Each case cuts Nosana off from its k-th model call. `hybrid` is `MODEL_TYPE=HYBRID`
(routing and chat on qwen3.5:2b-q4_K_M with an 8,192-token window, planning and tools
on Nosana); `nosana` has no fallback. When a failure stops the task, the harness replies
`continue` (Nosana stays down) or `retry` (Nosana is back first).

## Totals

| Group | Cases | Passed | Crashed | Stopped cleanly | Steps redone after recovery |
|---|---|---|---|---|---|
| T4 hybrid: refused → continue | 7 | 0 | 0 | 5 | 8 |
| T5 hybrid: refused → continue | 3 | 2 | 0 | 1 | 0 |
| T4 hybrid: refused → retry | 1 | 1 | 0 | 1 | 0 |
| T4 hybrid: 503 → retry | 1 | 1 | 0 | 1 | 0 |
| T4 hybrid: timeout → retry | 1 | 1 | 0 | 1 | 0 |
| T4 hybrid: midstream → retry | 1 | 1 | 0 | 1 | 0 |
| T4 hybrid: 401 → continue | 1 | 0 | 0 | 1 | 2 |
| T4 nosana: refused → retry | 1 | 1 | 0 | 1 | 0 |
| T1 hybrid: local model down | 1 | 1 | 0 | 0 | 0 |
| T4 hybrid: local model down | 1 | 0 | 0 | 0 | 0 |

## Cases

| Case | Cut at | Failure | Reply | Result | Checks | Calls (Nosana / local) | Steps kept | Steps redone | Failed Nosana requests | Local calls over window (est.) | Time (s) | Nosana cost |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `T4-cut1-refused-hybrid-continue` | 1 (plan) | refused | — | kept going → ❌ checks failed | 0/4 | 0 / 3 | 0 | 0 | 2 | 0 | 18 | $0.0000 |
| `T4-cut2-refused-hybrid-continue` | 2 (execute) | refused | continue | stopped → continue → ❌ checks failed | 0/4 | 1 / 7 | 0 | 0 | 2 | 0 | 182 | $0.0185 |
| `T4-cut3-refused-hybrid-continue` | 3 (execute) | refused | continue | stopped → continue → ❌ checks failed | 0/4 | 2 / 7 | 1 | 1 | 2 | 0 | 234 | $0.0238 |
| `T4-cut4-refused-hybrid-continue` | 4 (execute) | refused | continue | stopped → continue → ❌ checks failed | 0/4 | 3 / 6 | 2 | 1 | 2 | 0 | 207 | $0.0216 |
| `T4-cut5-refused-hybrid-continue` | 5 (—) | refused | — | no cut (finished first) → ❌ checks failed | 0/4 | 0 / 2 | 0 | 0 | 0 | 0 | 24 | $0.0000 |
| `T4-cut6-refused-hybrid-continue` | 6 (execute) | refused | continue | stopped → continue → ❌ checks failed | 1/4 | 5 / 5 | 4 | 2 | 2 | 0 | 214 | $0.0222 |
| `T4-cut7-refused-hybrid-continue` | 7 (execute) | refused | continue | stopped → continue → ❌ checks failed | 3/4 | 6 / 10 | 5 | 4 | 2 | 0 | 278 | $0.0311 |
| `T5-cut1-refused-hybrid-continue` | 1 (plan) | refused | — | kept going → ✅ passed | 4/4 | 0 / 6 | 3 | 0 | 2 | 0 | 28 | $0.0000 |
| `T5-cut2-refused-hybrid-continue` | 2 (execute) | refused | continue | stopped → continue → ❌ checks failed | 3/4 | 1 / 5 | 0 | 0 | 2 | 0 | 67 | $0.0060 |
| `T5-cut3-refused-hybrid-continue` | 3 (—) | refused | — | no cut (finished first) → ✅ passed | 4/4 | 2 / 1 | 1 | 0 | 0 | 0 | 11 | $0.0019 |
| `T4-cut3-refused-hybrid-retry` | 3 (execute) | refused | retry | stopped → retry → ✅ passed | 4/4 | 7 / 1 | 1 | 0 | 2 | 0 | 218 | $0.0331 |
| `T4-cut3-503-hybrid-retry` | 3 (execute) | 503 | retry | stopped → retry → ✅ passed | 4/4 | 8 / 1 | 2 | 0 | 2 | 0 | 113 | $0.0214 |
| `T4-cut3-timeout-hybrid-retry` | 3 (execute) | timeout | retry | stopped → retry → ✅ passed | 4/4 | 7 / 1 | 1 | 0 | 2 (real wait ≈ 120s) | 0 | 230 | $0.0358 |
| `T4-cut3-midstream-hybrid-retry` | 3 (execute) | midstream | retry | stopped → retry → ✅ passed | 4/4 | 6 / 1 | 1 | 0 | 1 | 0 | 228 | $0.0332 |
| `T4-cut3-401-hybrid-continue` | 3 (execute) | 401 | continue, continue | stopped → continue → continue → ❌ checks failed | 2/4 | 2 / 12 | 1 | 2 | 1 | 0 | 277 | $0.0231 |
| `T4-cut3-refused-nosana-retry` | 3 (execute) | refused | retry | stopped → retry → ✅ passed | 4/4 | 8 / 0 | 0 | 0 | 2 | 0 | 161 | $0.0260 |
| `T1-localdown-hybrid` | 0 (—) | none | — | local model down → ✅ passed | 4/4 | 2 / 0 | 0 | 0 | 0 | 0 | 9 | $0.0005 |
| `T4-localdown-hybrid` | 0 (—) | none | — | local model down → ❌ checks failed | 3/4 | 7 / 0 | 4 | 0 | 0 | 0 | 353 | $0.0502 |

## Timelines

`N` = Nosana, `L` = local, ✂ = where Nosana was cut, ⏎ = the harness's reply after a stop.
`(6.2K!)` = the prompt sent to the local model, estimated at 0.282 tokens per character
(measured on Nosana's exact counts); `!` = over the local window.

**T4-cut1-refused-hybrid-continue**: classify:L✓(0.6K) → ✂ plan:N✗ → plan:L✓(0.7K) → execute:L✓[run_deploy_script](4.1K)


**T4-cut2-refused-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → ✂ execute:N✗ → ⏎ continue → execute:L✓[create_project_folder](4.2K) → execute:L✓[create_project_folder](4.3K) → execute:L✓[create_project_folder](4.4K) → execute:L✓[create_project_folder](4.5K) → execute:L✓[run_command](4.6K) → execute:L✓[run_command](4.7K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`

**T4-cut3-refused-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[find_folder] → ✂ execute:N✗ → ⏎ continue → execute:L✓[find_folder](4.2K) → execute:L✓[create_project_folder](4.3K) → execute:L✓[create_folder](4.4K) → execute:L✓[run_command](4.6K) → execute:L✓[write_file](4.7K) → execute:L✓[run_command](5.6K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/static/index.html (2672 B)

**T4-cut4-refused-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[run_command] → ✂ execute:N✗ → ⏎ continue → execute:L✓[create_project_folder](4.3K) → execute:L✓[create_project_folder](4.4K) → execute:L✓[write_file](4.5K) → execute:L✓[write_file](5.3K) → execute:L✓(5.5K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/app.py (2156 B), calc_app/requirements.txt (60 B)

**T4-cut5-refused-hybrid-continue**: classify:L✓(0.6K) → conversational:L✓(0.3K)


**T4-cut6-refused-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[run_command] → execute:N✓[write_file] → ✂ execute:N✗ → ⏎ continue → execute:L✓[run_command](4.4K) → execute:L✓[write_file](4.5K) → execute:L✓[write_file](5.4K) → execute:L✓(6.5K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/app.py (3496 B), calc_app/static/index.html (2614 B)

**T4-cut7-refused-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → ✂ execute:N✗ → ⏎ continue → execute:L✓[create_project_folder](4.5K) → execute:L✓[create_folder](4.6K) → execute:L✓[create_folder](4.8K) → execute:L✓[get_files_info](5.0K) → execute:L✓[create_project_folder](5.1K) → execute:L✓[create_folder](5.2K) → execute:L✓[run_command](5.4K) → execute:L✓[run_command](5.5K) → execute:L✓[run_command](5.6K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/app.py (2051 B), calc_app/static/css/styles.css (871 B), calc_app/static/index.html (674 B)

**T5-cut1-refused-hybrid-continue**: classify:L✓(0.5K) → ✂ plan:N✗ → plan:L✓(0.6K) → execute:L✓[detect_operating_system](4.4K) → execute:L✓[detect_operating_system](3.9K) → execute:L✓[check_internet](3.9K) → execute:L✓[install_package](3.9K)


**T5-cut2-refused-hybrid-continue**: classify:L✓(0.5K) → plan:N✓ → ✂ execute:N✗ → ⏎ continue → execute:L✓[detect_operating_system](4.0K) → execute:L✓[run_command](4.1K) → execute:L✓[run_command](4.2K) → execute:L✓[run_command](4.3K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`

**T5-cut3-refused-hybrid-continue**: classify:L✓(0.5K) → execute:N✓[check_internet] → execute:N✓[install_package]


**T4-cut3-refused-hybrid-retry**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → ⏎ retry → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/app.py (2992 B), calc_app/requirements.txt (33 B), calc_app/static/index.html (2191 B)

**T4-cut3-503-hybrid-retry**: classify:L✓(0.6K) → execute:N✓[find_folder] → execute:N✓[create_project_folder] → ✂ execute:N✗ → ⏎ retry → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[get_files_info] → execute:N✓

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: InternalServerError: Error code: 503 - {'error': {'message': 'simulated: no GPU is serving this model'}}.`
- files: calc_app/app.py (2758 B), calc_app/requirements.txt (29 B), calc_app/static/index.html (4019 B)

**T4-cut3-timeout-hybrid-retry**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → ⏎ retry → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APITimeoutError: Request timed out.`
- files: calc_app/app.py (2697 B), calc_app/requirements.txt (43 B), calc_app/static/index.html (3366 B)

**T4-cut3-midstream-hybrid-retry**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[run_command] → ✂ execute:N✗ → ⏎ retry → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: ReadError: simulated: connection dropped mid-reply.`
- files: calc_app/app.py (2394 B), calc_app/requirements.txt (59 B), calc_app/static/index.html (2816 B)

**T4-cut3-401-hybrid-continue**: classify:L✓(0.6K) → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → ⏎ continue → execute:L✓[create_folder](4.3K) → execute:L✓[create_project_folder](4.4K) → execute:L✓[create_folder](4.5K) → execute:L✓[create_project_folder](4.8K) → execute:L✓[create_project_folder](4.9K) → execute:L✓[write_file](5.0K) → execute:L✗(ResponseError) → ⏎ continue → execute:L✓[write_file](6.1K) → execute:L✓[write_file](6.4K) → execute:L✓[list_directory](6.5K) → execute:L✓[get_files_info](6.7K) → execute:L✓(6.8K)

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: AuthenticationError: Error code: 401 - {'error': {'message': 'simulated: invalid API key or no credits left'}}.`
- files: calc_app/app.py (2768 B), calc_app/requirements.txt (25 B), calc_app/static/index.html (1160 B)

**T4-cut3-refused-nosana-retry**: classify:N✓ → plan:N✓ → ✂ execute:N✗ → ⏎ retry → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[get_files_info] → execute:N✓

- the agent stopped and said: `Nosana (qwen/qwen3.8-27b) stopped: APIConnectionError: Connection error.`
- files: calc_app/app.py (2891 B), calc_app/requirements.txt (33 B), calc_app/static/index.html (2329 B)

**T1-localdown-hybrid**: classify:L✗(ConnectError) → classify:N✓ → conversational:N✓


**T4-localdown-hybrid**: classify:L✗(ConnectError) → classify:N✓ → plan:N✓ → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- files: calc_app/app.py (2787 B), calc_app/requirements.txt (16 B), calc_app/static/index.html (3699 B)

Nosana cost of all cases: $0.3485 (tokens × $0.20 / $2.00 per 1M in / out).
