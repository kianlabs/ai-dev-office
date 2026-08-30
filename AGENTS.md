# AGENTS.md — AI Dev Office

Aturan operasional untuk coding agent yang bekerja di repository ini.

Dokumen ini menjelaskan arsitektur dan guardrail yang SUDAH ADA saat ini.
Jangan menganggap roadmap atau ide masa depan sebagai fitur yang sudah diimplementasikan.

## Apa project ini

AI Dev Office adalah environment pengembangan multi-agent yang berjalan lokal.

- Browser hanya sebagai UI, telemetry, task composer, Activity Feed, dan visual 3D office.
- Seluruh eksekusi agent berjalan lokal di mesin ini.
- Project ini bukan SaaS/public runtime.
- Backend/runtime lokal adalah sumber kebenaran eksekusi.

## Struktur repository

- `apps/api/` — backend FastAPI, routes, engine wiring, persistence.
- `apps/web/` — UI control room Next.js dan 3D office.
- `packages/agent-core/` — engine, registry, execution context, intent.
- `packages/shared/` — shared model dan workspace preparation.
- `packages/tools/` — utilitas/tool lokal bersama.
- `agents/atlas/` — orchestration dan conversation.
- `agents/scout/` — research/evidence gathering.
- `agents/forge/` — implementasi melalui Hermes.
- `agents/qa/` — deterministic verification.
- `agents/pulse/` — deterministic local monitoring.
- `workspaces/` — isolated workspace per task.
- `data/` — persistence SQLite lokal.

## Role dan kontrak agent

### ATLAS

ATLAS adalah orchestrator dan conversational layer.

Tanggung jawab:

- mengklasifikasikan intent
- menjaga context percakapan/plan secara bounded
- memilih specialist workflow
- melakukan dispatch specialist
- menurunkan hasil/status workflow dari evidence

ATLAS TIDAK BOLEH:

- menjalankan arbitrary shell
- langsung mengedit source code target
- mengarang hasil verification
- mempercayai narasi specialist sebagai runtime fact

Intent saat ini:

- `CHAT`
- `PLAN`
- `RESEARCH`
- `IMPLEMENT`
- `TEST`
- `MONITOR`
- `NEEDS_INPUT`

### SCOUT

SCOUT adalah agent read-only untuk research dan pengumpulan evidence.

SCOUT boleh:

- membaca file
- memeriksa struktur repository
- memeriksa manifest/config
- mengumpulkan evidence bounded
- membuat research summary

SCOUT tidak boleh menulis ke target workspace/source repository.

### FORGE

FORGE melakukan implementasi melalui Hermes.

Aturan:

- hanya bekerja di authoritative isolated execution workspace
- tidak boleh langsung mengubah source repository asli
- output FORGE adalah agent report, bukan verification truth
- perubahan filesystem dan diff lebih authoritative daripada narasi FORGE

### QA

QA adalah deterministic verifier.

QA adalah satu-satunya sumber kebenaran verification implementasi.

Hasil yang valid:

- `PASS`
- `FAIL`
- `NOT_VERIFIED`
- `INTERRUPTED`

Aturan:

- `PASS` wajib punya evidence verification nyata
- `NOT_VERIFIED` BUKAN `PASS`
- jangan mengubah ketiadaan check menjadi fake success
- FORGE berkata "tests passed" tidak dianggap sebagai QA evidence

### PULSE

PULSE adalah deterministic read-only local monitor.

PULSE boleh:

- cek explicit local TCP port
- probe loopback HTTP health endpoint
- memeriksa process lokal yang dikonfigurasi
- membaca tail log secara bounded

PULSE secara default TIDAK BOLEH:

- kill process
- restart service
- mengubah application state
- melakukan arbitrary port scan

## Routing saat ini

- `CHAT` → ATLAS saja
- `PLAN` → ATLAS saja
- `RESEARCH` → SCOUT
- `IMPLEMENT` → FORGE → QA, SCOUT optional
- `TEST` → QA
- `MONITOR` → PULSE
- `NEEDS_INPUT` → ATLAS saja

`CHAT`, `PLAN`, dan `NEEDS_INPUT` tidak boleh membuat implementation workspace.

Repair loop hanya boleh terjadi pada workflow `IMPLEMENT` yang memang sudah melakukan percobaan implementasi melalui FORGE.

## Aturan workspace

`ctx.shared["workspace_meta"].workspace_path` adalah authoritative execution workspace.

Gunakan nilai tersebut jika tersedia.
Jangan menebak atau membangun ulang path execution sendiri.

Perilaku target:

- clean git target → isolated git worktree
- non-git target → bounded safe copy
- tidak ada target → disposable empty workspace
- dirty git target → fail safely

Jangan pernah langsung mengubah original target source repository.

Jangan bypass dirty-repository protection.

Saat ini tidak ada implicit permission untuk meng-apply hasil isolated workspace kembali ke source repository.

Biarkan hasil tetap reviewable sampai ada explicit approved apply/integration action.

Jangan sembarangan menghapus git worktree atau metadata terkait.

## Aturan Git — WAJIB

Jangan pernah:

- menjalankan `git add .`
- otomatis stash perubahan user
- reset source repository
- checkout menimpa perubahan user
- membuang untracked file
- menyentuh stash lama user
- commit kecuali user secara eksplisit meminta
- push kecuali user secara eksplisit meminta

Jika staging diperlukan, stage explicit path saja.

Pertahankan file user dan untracked asset yang tidak terkait.

## Hermes / execution

FORGE berjalan melalui Hermes di dalam sandbox yang dikonfigurasi.

Aturan:

- jangan ubah model/provider Hermes kecuali diminta eksplisit
- gunakan default dari Hermes config jika tidak ada execution override
- jangan mencetak credential Hermes
- jangan membunuh global Hermes gateway
- cancellation harus hanya menarget task/process group yang relevan

Gunakan mekanisme cancellation per-task yang sudah ada seperti:

- `cancel_task_execution`
- `cancel_qa_execution`
- `cancel_pulse_execution`

JANGAN gunakan Uvicorn `--reload` selama real agent execution.

Reload bisa me-restart FastAPI saat agent sedang menulis workspace dan menyebabkan task orphan.

## Runtime truth

Aturan utama:

> AGENT CLAIM != SYSTEM FACT

Activity Feed adalah telemetry/projection.
Activity Feed bukan sumber kebenaran task.

Narasi specialist seperti:

- "implementasi berhasil"
- "test lulus"
- "service sehat"

tidak boleh langsung menjadi authoritative state.

Utamakan observed facts seperti:

- execution workspace state
- changed files
- git diff
- process exit code
- QA check
- HTTP probe result
- process probe result

Jika narasi agent konflik dengan runtime evidence, runtime evidence menang.

ATLAS tidak boleh menyatakan sesuatu sudah dites, verified, sehat, atau berhasil diimplementasikan tanpa evidence yang mendukung.

## Semantik verification

Untuk workflow implementasi:

FORGE selesai + QA PASS/verified
→ VERIFIED

FORGE selesai + QA NOT_VERIFIED
→ REVIEW_REQUIRED

FORGE selesai + QA FAIL
→ bounded repair jika diizinkan, jika tidak → FAILED

FORGE interrupted
→ INTERRUPTED

`FORGE completed` saja tidak pernah berarti `VERIFIED`.

Jangan emit pesan seperti:

`workflow completed successfully`

jika QA sebenarnya `NOT_VERIFIED`.

## Semantik monitoring

PULSE hanya melaporkan observed local health.

Contoh:

- HTTP 200 dari configured health endpoint → evidence
- configured port tertutup → evidence
- process PID tidak ada → evidence

Jangan menyimpulkan health dari narasi teks.
Jangan mengarang monitoring target.

## Secret / credential

Jangan pernah print, expose, copy ke prompt, commit, atau persist value sensitif seperti:

- isi `.env`
- API key
- access token
- credential Hermes
- SSH private key
- password
- konfigurasi yang mengandung secret

Jangan masukkan secret ke:

- Activity Feed
- agent report
- evidence payload
- task summary
- log yang ditampilkan ke UI

## Persistence

Migration SQLite harus additive dan idempotent.

Row/history lama harus tetap bisa dibaca setelah perubahan schema.

Jangan menghapus atau recreate database sebagai jalan pintas untuk memperbaiki migration.

Jangan diam-diam menghapus task history.

## Guardrail 3D office

Jangan redesign atau mengubah besar-besaran hal berikut kecuali diminta eksplisit:

- layout 3D office
- camera
- setup Mixamo
- assignment karakter agent
- navigation behavior
- ambient office behavior

Pertahankan untracked Mixamo/FBX/cubicle asset di:

`apps/web/public/models/`

Jangan hapus atau overwrite asset tersebut saat mengerjakan hal lain.

## Validation

Backend:

    .venv/bin/pytest apps/api/tests -q

Frontend:

    cd apps/web
    npm run typecheck
    npm run lint
    npx vitest run

Setelah frontend validation:

    cd ~/ai-dev-office
    git restore apps/web/tsconfig.tsbuildinfo 2>/dev/null || true
    git diff --check

## Sebelum melaporkan task selesai

Coding agent wajib:

1. memeriksa diff aktual
2. menjalankan validation yang relevan
3. membedakan verified facts dari agent claim
4. melaporkan limitation atau hasil yang belum verified secara eksplisit
5. tidak menyentuh file user yang tidak terkait
6. tidak commit/push kecuali sudah diizinkan user
