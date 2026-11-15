# zkzkAgent: Nosana dropping out mid-task — 2026-11-15-dropout

Each case cuts Nosana off from its k-th model call. `shipped` is the agent as it is today;
`fb2b` / `fb4b` fall back to qwen3.5:2b-q4_K_M / qwen3:4b with LangChain's with_fallbacks().

## Cases

| Case | Cut at | Failure | Result | Checks | Calls (Nosana / local) | Failed Nosana requests | Local calls over 4K (est.) | Files on disk | Time (s) | Nosana cost |
|---|---|---|---|---|---|---|---|---|---|---|
| `T4-cut1-refused-shipped` | 1 (classify) | refused | ✖ crashed: APIConnectionError → ❌ checks failed | 0/4 | 0 / 0 | 6 | 0 | 0 | 3 | $0.0000 |
| `T4-cut2-midstream-shipped` | 2 (plan) | midstream | ✖ crashed: ReadError → ❌ checks failed | 0/4 | 1 / 0 | 1 | 0 | 0 | 112 | $0.0003 |
| `T4-cut4-refused-shipped-retry` | 4 (execute) | refused | ✖ crashed, retried → ✅ passed | 4/4 | 8 / 0 | 3 | 0 | 3 | 220 | $0.0348 |
| `T4-cut4-503-shipped` | 4 (execute) | 503 | ✖ crashed: InternalServerError → ❌ checks failed | 0/4 | 3 / 0 | 3 | 0 | 0 | 67 | $0.0092 |
| `T4-cut4-timeout-shipped` | 4 (execute) | timeout | ✖ crashed: APITimeoutError → ❌ checks failed | 0/4 | 3 / 0 | 3 (real wait ≈ 360s) | 0 | 0 | 180 | $0.0238 |
| `T4-cut4-401-shipped` | 4 (execute) | 401 | ✖ crashed: AuthenticationError → ❌ checks failed | 0/4 | 3 / 0 | 1 | 0 | 0 | 186 | $0.0249 |
| `T4-cut4-midstream-shipped` | 4 (execute) | midstream | ✖ crashed: ReadError → ❌ checks failed | 0/4 | 3 / 0 | 1 | 0 | 0 | 106 | $0.0143 |
| `T4-cut1-refused-fb2b` | 1 (classify) | refused | ✖ crashed: APIConnectionError (really the local model: ResponseError) → ❌ checks failed | 0/4 | 0 / 5 | 18 | 0 | 0 | 40 | $0.0000 |
| `T4-cut2-refused-fb2b` | 2 (plan) | refused | kept going → ❌ checks failed | 0/4 | 1 / 6 | 18 | 1 | 0 | 47 | $0.0003 |
| `T4-cut3-refused-fb2b` | 3 (execute) | refused | kept going → ❌ checks failed | 0/4 | 2 / 1 | 3 | 1 | 0 | 144 | $0.0106 |
| `T4-cut4-refused-fb2b` | 4 (execute) | refused | ✖ crashed: APIConnectionError (really the local model: ResponseError) → ❌ checks failed | 0/4 | 3 / 0 | 3 | 0 | 0 | 107 | $0.0137 |
| `T4-cut5-refused-fb2b` | 5 (execute) | refused | ✖ crashed: ReadTimeout (really the local model: ReadTimeout) → ❌ checks failed | 0/4 | 4 / 1 | 6 | 1 | 0 | 189 | $0.0159 |
| `T4-cut6-refused-fb2b` | 6 (execute) | refused | kept going → ❌ checks failed | 3/4 | 5 / 1 | 3 | 1 | 2 | 161 | $0.0222 |
| `T4-cut7-refused-fb2b` | 7 (execute) | refused | ✖ crashed: APIConnectionError (really the local model: ReadTimeout) → ❌ checks failed | 3/4 | 6 / 0 | 3 | 0 | 2 | 168 | $0.0168 |
| `T4-cut8-refused-fb2b` | 8 (—) | refused | no cut (finished first) → ✅ passed | 4/4 | 7 / 0 | 0 | 0 | 3 | 144 | $0.0228 |
| `T5-cut1-refused-fb2b` | 1 (classify) | refused | kept going → ✅ passed | 4/4 | 0 / 5 | 15 | 0 | 0 | 29 | $0.0000 |
| `T5-cut2-refused-fb2b` | 2 (execute) | refused | kept going → ✅ passed | 4/4 | 1 / 1 | 3 | 0 | 0 | 10 | $0.0003 |
| `T5-cut3-refused-fb2b` | 3 (execute) | refused | kept going → ✅ passed | 4/4 | 2 / 1 | 3 | 0 | 0 | 12 | $0.0012 |
| `T5-cut4-refused-fb2b` | 4 (—) | refused | no cut (finished first) → ✅ passed | 4/4 | 3 / 0 | 0 | 0 | 0 | 9 | $0.0022 |
| `T5-cut5-refused-fb2b` | 5 (execute) | refused | kept going → ✅ passed | 4/4 | 4 / 1 | 3 | 0 | 0 | 16 | $0.0022 |
| `T4-cut4-timeout-fb2b` | 4 (execute) | timeout | ✖ crashed: APITimeoutError (really the local model: ResponseError) → ❌ checks failed | 0/4 | 3 / 5 | 18 (real wait ≈ 2160s) | 5 | 1 | 202 | $0.0229 |
| `T4-cut4-401-fb2b` | 4 (execute) | 401 | kept going → ❌ checks failed | 0/4 | 3 / 8 | 8 | 8 | 3 | 151 | $0.0151 |
| `T4-cut4-midstream-fb2b` | 4 (execute) | midstream | ✖ crashed: ReadError → ❌ checks failed | 0/4 | 3 / 0 | 1 | 0 | 0 | 146 | $0.0194 |
| `T4-cut1-refused-fb4b` | 1 (classify) | refused | kept going → ❌ checks failed | 0/4 | 0 / 3 | 9 | 1 | 0 | 426 | $0.0000 |
| `T4-cut2-refused-fb4b` | 2 (plan) | refused | kept going → ❌ checks failed | 0/4 | 1 / 2 | 6 | 1 | 0 | 363 | $0.0004 |
| `T4-cut3-refused-fb4b` | 3 (execute) | refused | kept going → ❌ checks failed | 0/4 | 2 / 1 | 3 | 1 | 0 | 320 | $0.0191 |
| `T4-cut4-refused-fb4b` | 4 (execute) | refused | kept going → ❌ checks failed | 1/4 | 3 / 5 | 15 | 3 | 2 | 386 | $0.0115 |
| `T4-cut5-refused-fb4b` | 5 (execute) | refused | kept going → ❌ checks failed | 3/4 | 2 / 5 | 9 | 3 | 3 | 508 | $0.0076 |
| `T4-cut6-refused-fb4b` | 6 (execute) | refused | kept going → ✅ passed | 4/4 | 5 / 3 | 9 | 3 | 3 | 192 | $0.0111 |
| `T4-cut7-refused-fb4b` | 7 (execute) | refused | kept going → ✅ passed | 4/4 | 6 / 1 | 3 | 1 | 3 | 296 | $0.0309 |
| `T4-cut8-refused-fb4b` | 8 (execute) | refused | kept going → ✅ passed | 4/4 | 7 / 2 | 6 | 2 | 3 | 198 | $0.0200 |
| `T5-cut1-refused-fb4b` | 1 (classify) | refused | kept going → ❌ checks failed | 3/4 | 0 / 4 | 12 | 0 | 0 | 235 | $0.0000 |
| `T5-cut2-refused-fb4b` | 2 (execute) | refused | kept going → ✅ passed | 4/4 | 1 / 3 | 9 | 0 | 0 | 201 | $0.0004 |
| `T5-cut3-refused-fb4b` | 3 (execute) | refused | kept going → ✅ passed | 4/4 | 2 / 1 | 3 | 0 | 0 | 59 | $0.0012 |
| `T5-cut4-refused-fb4b` | 4 (—) | refused | no cut (finished first) → ✅ passed | 4/4 | 3 / 0 | 0 | 0 | 0 | 15 | $0.0030 |
| `T5-cut5-refused-fb4b` | 5 (—) | refused | no cut (finished first) → ✅ passed | 4/4 | 3 / 0 | 0 | 0 | 0 | 11 | $0.0024 |

## Timelines

`N` = Nosana, `L` = local, ✂ = where Nosana was cut. `(6.2K!)` = the history sent to the local model,
estimated at 0.280 tokens per character (measured on Nosana's exact counts); `!` = over the 4,096 window.
Ollama keeps only what fits: it drops older messages, or cuts the prompt itself.

**T4-cut1-refused-shipped**: ✂ classify:N✗ → conversational:N✗

- the user typed `Create a project folder called calc_app inside /home/aloha-z` and got: `APIConnectionError: Connection error.`

**T4-cut2-midstream-shipped**: classify:N✓ → ✂ plan:N✗

- the user typed `Create a project folder called calc_app inside /home/aloha-z` and got: `ReadError: simulated: connection dropped mid-reply`

**T4-cut4-refused-shipped-retry**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- the user typed `ok` and got: `APIConnectionError: Connection error.`
- files: calc_app/app.py (2805 B), calc_app/requirements.txt (16 B), calc_app/static/index.html (2561 B)

**T4-cut4-503-shipped**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗

- the user typed `ok` and got: `InternalServerError: Error code: 503 - {'error': {'message': 'simulated: no GPU is serving this model'}}`

**T4-cut4-timeout-shipped**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗

- the user typed `ok` and got: `APITimeoutError: Request timed out.`

**T4-cut4-401-shipped**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗

- the user typed `ok` and got: `AuthenticationError: Error code: 401 - {'error': {'message': 'simulated: invalid API key or no credits left'}}`

**T4-cut4-midstream-shipped**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗

- the user typed `ok` and got: `ReadError: simulated: connection dropped mid-reply`

**T4-cut1-refused-fb2b**: ✂ classify:N✗ → classify:L✓(0.6K) → plan:N✗ → plan:L✓(0.7K) → execute:N✗ → execute:L✓[create_project_folder](3.6K) → execute:N✗ → execute:L✓[write_file](3.5K) → execute:N✗ → execute:L✓[write_file](3.7K) → execute:N✗ → execute:L✗(ResponseError)

- the user typed `ok` and got: `APIConnectionError: Connection error.`
- the local model's own error, hidden behind Nosana's: `ResponseError: XML syntax error on line 32: element <function> closed by </parameter> (status code: 500)`

**T4-cut2-refused-fb2b**: classify:N✓ → ✂ plan:N✗ → plan:L✓(0.7K) → execute:N✗ → execute:L✓[create_project_folder](3.7K) → execute:N✗ → execute:L✓[create_project_folder](3.6K) → execute:N✗ → execute:L✓[create_project_folder](3.7K) → execute:N✗ → execute:L✓[write_file](3.8K) → execute:N✗ → execute:L✓(4.2K!)


**T4-cut3-refused-fb2b**: classify:N✓ → plan:N✓ → ✂ execute:N✗ → execute:L✓(7.5K!)


**T4-cut4-refused-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → execute:L✗(ResponseError)

- the user typed `ok` and got: `APIConnectionError: Connection error.`
- the local model's own error, hidden behind Nosana's: `ResponseError: XML syntax error on line 6: element <function> closed by </parameter> (status code: 500)`

**T4-cut5-refused-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[get_files_info] → execute:N✓[run_command] → ✂ execute:N✗ → execute:L✓[create_project_folder](4.4K!) → execute:N✗ → execute:L✗(ReadTimeout)

- the user typed `ok` and got: `ReadTimeout: timed out`
- the local model's own error, hidden behind Nosana's: `ReadTimeout: timed out`

**T4-cut6-refused-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → ✂ execute:N✗ → execute:L✓(7.1K!)

- files: calc_app/app.py (1874 B), calc_app/static/index.html (4807 B)

**T4-cut7-refused-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file] → ✂ execute:N✗ → execute:L✗(ReadTimeout)

- the user typed `ok` and got: `APIConnectionError: Connection error.`
- the local model's own error, hidden behind Nosana's: `ReadTimeout: timed out`
- files: calc_app/app.py (2367 B), calc_app/static/index.html (2845 B)

**T4-cut8-refused-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓

- files: calc_app/app.py (3067 B), calc_app/requirements.txt (35 B), calc_app/static/index.html (4682 B)

**T5-cut1-refused-fb2b**: ✂ classify:N✗ → classify:L✓(0.5K) → conversational:N✗ → conversational:L✓[detect_operating_system](2.6K) → classify:N✗ → classify:L✓(0.5K) → execute:N✗ → execute:L✓[detect_operating_system](3.2K) → execute:N✗ → execute:L✓[install_package](3.2K)


**T5-cut2-refused-fb2b**: classify:N✓ → ✂ execute:N✗ → execute:L✓[install_package](3.1K)


**T5-cut3-refused-fb2b**: classify:N✓ → execute:N✓[check_internet] → ✂ execute:N✗ → execute:L✓[install_package](3.2K)


**T5-cut4-refused-fb2b**: classify:N✓ → execute:N✓[check_internet] → execute:N✓[install_package]


**T5-cut5-refused-fb2b**: classify:N✓ → execute:N✓[check_internet] → execute:N✓ → classify:N✓ → ✂ execute:N✗ → execute:L✓[install_package](3.2K)


**T4-cut4-timeout-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → execute:L✓[create_project_folder](5.3K!) → execute:N✗ → execute:L✓[create_project_folder](5.4K!) → execute:N✗ → execute:L✓[create_project_folder](5.5K!) → execute:N✗ → execute:L✓[write_file](5.7K!) → execute:N✗ → execute:L✓[open_file](5.9K!) → execute:N✗ → execute:L✗(ResponseError)

- the user typed `ok` and got: `APITimeoutError: Request timed out.`
- the local model's own error, hidden behind Nosana's: `ResponseError: XML syntax error on line 6: element <function> closed by </parameter> (status code: 500)`
- files: calc_app/backend/main.py (495 B)

**T4-cut4-401-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗ → execute:L✓[write_file](5.0K!) → execute:N✗ → execute:L✓[write_file](5.2K!) → ⚠write_file✗ → execute:N✗ → execute:L✓[write_file](5.4K!) → ⚠write_file✗ → execute:N✗ → execute:L✓[write_file](5.7K!) → execute:N✗ → execute:L✓[write_file](5.8K!) → execute:N✗ → execute:L✓[open_vscode](5.9K!) → execute:N✗ → execute:L✓[run_deploy_script](6.0K!) → execute:N✗ → execute:L✓(6.1K!)

- files: calc_app/calc_app/app.js (251 B), calc_app/calc_app/main.js (232 B), calc_app/calc_app/start (13 B)

**T4-cut4-midstream-fb2b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → ✂ execute:N✗

- the user typed `ok` and got: `ReadError: simulated: connection dropped mid-reply`

**T4-cut1-refused-fb4b**: ✂ classify:N✗ → classify:L✓(0.6K) → plan:N✗ → plan:L✓(0.7K) → execute:N✗ → execute:L✓(5.8K!)


**T4-cut2-refused-fb4b**: classify:N✓ → ✂ plan:N✗ → plan:L✓(0.7K) → execute:N✗ → execute:L✓(5.0K!)


**T4-cut3-refused-fb4b**: classify:N✓ → plan:N✓ → ✂ execute:N✗ → execute:L✓(6.6K!)


**T4-cut4-refused-fb4b**: classify:N✓ → plan:N✓ → execute:N✓[run_command] → ✂ execute:N✗ → execute:L✓[create_project_folder](4.0K) → execute:N✗ → execute:L✓[run_command](4.1K) → execute:N✗ → execute:L✓[write_file](4.1K!) → execute:N✗ → execute:L✓[write_file](4.3K!) → execute:N✗ → execute:L✓(4.7K!)

- files: calc_app/app.py (450 B), calc_app/static/index.html (888 B)

**T4-cut5-refused-fb4b**: classify:N✗ → classify:L✓(0.6K) → plan:N✗ → plan:L✓(0.7K) → execute:N✓[run_command] → execute:N✓[write_file] → ✂ execute:N✗ → execute:L✓[write_file](4.2K!) → execute:N✗ → execute:L✓[write_file](4.5K!) → execute:N✗ → execute:L✓(4.6K!)

- files: calc_app/app.py (952 B), calc_app/requirements.txt (15 B), calc_app/static/index.html (518 B)

**T4-cut6-refused-fb4b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → ✂ execute:N✗ → execute:L✓[write_file](5.2K!) → execute:N✗ → execute:L✓[open_vscode](5.3K!) → execute:N✗ → execute:L✓(5.4K!)

- files: calc_app/app.py (2782 B), calc_app/requirements.txt (25 B), calc_app/static/index.html (562 B)

**T4-cut7-refused-fb4b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[run_command] → execute:N✓[write_file] → execute:N✓[write_file,write_file] → ✂ execute:N✗ → execute:L✓(6.9K!)

- files: calc_app/app.py (2821 B), calc_app/requirements.txt (26 B), calc_app/static/index.html (1915 B)

**T4-cut8-refused-fb4b**: classify:N✓ → plan:N✓ → execute:N✓[create_project_folder] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[write_file] → execute:N✓[get_files_info] → ✂ execute:N✗ → execute:L✓[open_vscode](7.2K!) → execute:N✗ → execute:L✓(7.3K!)

- files: calc_app/app.py (2437 B), calc_app/requirements.txt (26 B), calc_app/static/index.html (2290 B)

**T5-cut1-refused-fb4b**: ✂ classify:N✗ → classify:L✓(0.5K) → execute:N✗ → execute:L✓(3.1K) → classify:N✗ → classify:L✓(0.5K) → execute:N✗ → execute:L✓(3.2K)


**T5-cut2-refused-fb4b**: classify:N✓ → ✂ execute:N✗ → execute:L✓(3.1K) → classify:N✗ → classify:L✓(0.5K) → execute:N✗ → execute:L✓[install_package](3.2K)


**T5-cut3-refused-fb4b**: classify:N✓ → execute:N✓[check_internet] → ✂ execute:N✗ → execute:L✓[install_package](3.2K)


**T5-cut4-refused-fb4b**: classify:N✓ → execute:N✓[check_internet] → execute:N✓[install_package]


**T5-cut5-refused-fb4b**: classify:N✓ → execute:N✓[check_internet] → execute:N✓[install_package]


Nosana cost of all cases: $0.3809 (tokens × $0.20 / $2.00 per 1M in / out).
