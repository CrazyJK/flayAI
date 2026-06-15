# 자막 생성(Subtitle) — flayAI 통합 계획

> instance 영상의 **일본어 음성을 한국어 자막(.srt)으로** 만든다. 외부에서 opus 로 신청하면
> 큐에 쌓이고, **야간(사용자 취침 중)에 배치로 처리**한다. 야간 + GPU 양보 불필요 전제라
> 최고 품질 모델(faster-whisper large-v3)을 쓴다. 산출물은 **영상 옆 사이드카 `<stem>.srt`** —
> 외부 플레이어(flay 팝업/PotPlayer/VLC 등)가 동일 stem 규칙으로 자동 로드한다.
>
> 이 문서는 **확정된 계획**이며 일부는 **구현 완료**(아래 §구현 현황)다. flayAI 컨벤션
> ([CLAUDE.md](../CLAUDE.md), `.github/copilot-instructions.md`)에 맞춰 구현한다.

---

## 핵심 통찰 — Whisper 패스 하나가 셋을 떠받친다

영상에 Whisper 를 돌리면 **오디오에 정확히 박힌 일본어 발화 구간(타임스탬프)**이 나온다.
이 전사 결과 하나가 세 기능의 공통 토대다(전사는 `transcripts` 테이블에 캐시 → 재실행 회피):

```
                            ┌─ (A) 생성   : JP 텍스트 → KO 번역 → <stem>.srt
 video → Whisper(JP, VAD) ──┼─ (B) 싱크수정: 기존 KO 대사를 발화구간에 재정렬 → 타이밍 교정
   [transcripts 캐시]        └─ (C) 품질보정: JP↔(기존 KO) 정렬 → 번역메모리/용어집/평가셋
```

기존 instance 영상 중 **159개에 사람이 만든 한국어 팬자막**(아브자막/AVJAMAK 등)이 있다.
이게 단순 참조를 넘어 (C) **번역메모리(TM)·용어집·평가셋**이 되고, (B) 싱크수정의 정렬 기준이 된다.

---

## 구현 현황 (2026-06-15 기준)

**상태: phase 1(생성 파이프라인 + 신청 큐 + 야간 드레인) 구현·단위테스트 통과.**
환경 의존(faster-whisper 설치·모델 다운로드·GPU 실행)은 사용자 실행 필요(아래 §환경 단계).

### 확정 설계 (사용자 합의)
- 출력 = **영상 옆 사이드카 `<stem>.srt`**(기존 159개 관례 = 평범한 `.srt`). 한국어 단독.
- 워크플로 = **외부에서 opus 로 신청(큐 적재) → 야간 드레인이 순차 처리**. 즉시 처리 아님.
- 야간 배치 + **VRAM 양보 불필요** → STT 는 large-v3(최고 품질), 번역도 시간 들여 품질 우선.
- 사람 팬자막 보호: generate 는 **기존 `.srt` 있으면 건너뜀**. 싱크수정(resync)이 그쪽 담당.

### 단계(페이즈)
| 페이즈 | 내용 | 상태 |
|---|---|---|
| **1. 생성 + 큐 + 야간** | opus → 전사 → 번역(NLLB 재사용) → `.srt`. 신청 API + drain CLI + 야간 스크립트 | ✅ 구현 |
| **2. 번역 품질 보정** | ① JP↔KO 번역메모리 ✅ → ② LLM+few-shot 번역 ✅ → ③ 평가셋 대조 | 🔶 ①② 구현 |
| **3. 싱크 드리프트 수정** | 137개 드리프트 자막을 Whisper 발화구간에 DTW 재정렬 → 타이밍 교정 | ⬜ 예정 |

> 실측: 팬자막 보유 instance = **137편**(온라인+DB 기준). 1편(ABW-061) 시범 구축: JP 1085세그먼트 ×
> KO 1356큐 → **756쌍 채택 / 526 탈락**(유사도·길이 필터). 팬자막이 의역체라 sim 0.5~0.7대 —
> 이 "현지화된 말투"가 ②의 few-shot 학습 대상이다.

### 구현됨 ✅ (phase 1)
**서브시스템** (`packages/subtitler/`)
- `config.py` — `subtitle:` 블록 + 기본값 병합(stabilizer 패턴)
- `srt_io.py` — 인코딩 자동감지(UTF-8/CP949/EUC-KR) SRT 파싱·작성, 타임스탬프 변환, 크레딧 제거
- `db.py` — `subtitle_jobs`(신청 큐) + `transcripts`(전사 캐시) 스키마·CRUD. 인덱서 DB 공유
- `whisper_stt.py` — faster-whisper 래퍼(모듈 싱글톤·lazy, VAD, 진행콜백, unload)
- `translate.py` — 세그먼트 번역. phase1=기존 인덱서 NLLB(`translate_text`) 재사용(캐시 활용)
- `core.py` — 오케스트레이션(opus 해소 → 전사캐시 → generate). resync 는 phase 3 스텁
- `cli.py` — `enqueue` / `run`(단건 즉시) / `drain`(야간 배치)

**API** (`apps/api/routers/subtitle.py`, `apps/api/main.py`)
- `POST /api/subtitle/requests {opus, task}` — 외부 신청(opus 검증, 개방)
- `GET /api/subtitle/requests` · `GET /requests/{id}` — 큐/상태 폴링
- `POST /api/subtitle/drain` — 수동 드레인(서브프로세스) · `DELETE /requests/{id}` — 삭제 (둘 다 localhost 전용)

**운영** — `scripts/nightly_subtitle.ps1`(작업 스케줄러용, ASCII), `config.yaml subtitle:`, `.gitignore data/subtitle/`

### 처리 흐름 (영상 1개, generate)
1. `posters.video_path` 로 영상 경로 해소(오프라인/부재면 실패 처리).
2. 기존 `.srt` 있으면 **건너뜀**(사람 팬자막 보호).
3. 전사: faster-whisper(language=ja, vad_filter) → 세그먼트. `transcripts`(opus+model+mtime) 캐시.
4. 번역: 세그먼트별 JP→KO(`translate_text`, `translations` 캐시 → 반복 대사 1회만 번역).
5. 작성: `<stem>.srt` 원자적 기록. 출력 위치에 기존 파일 있으면 `<stem>.orig.srt` 로 1회 백업.

---

## 환경 단계 (사용자 실행 필요)

1. **의존성**: `pyproject.toml` 에 `faster-whisper>=1.1` 추가됨 → `uv lock` 후 사용자 `uv sync`.
   - CTranslate2 가 자체 CUDA12 libs(`nvidia-cublas/cudnn-cu12`)를 끌어온다. 과거 onnxruntime
     CPU/GPU 충돌 전례가 있어 **`uv sync` 후 GPU 인식 검증 권장**(`WhisperModel(..., device="cuda")`).
   - 정 깨지면 torch/CUDA 와 독립적인 `whisper.cpp`(ffmpeg 처럼 바이너리 의존)로 대체 가능.
2. **모델**: 최초 1회 HuggingFace 자동 다운로드(large-v3 ≈ 3GB). 빠르게: `config.yaml` `subtitle.model: large-v3-turbo`.
3. **야간 스케줄러 등록**: `scripts/nightly_subtitle.ps1` — nightly_index 와 시간을 어긋나게(예: 04:30)
   등록해 같은 GPU 동시 사용을 피한다. 스크립트 상단 schtasks 예시 참고.

## 사용 예

```powershell
# 단건 즉시 처리(수동 테스트 — 큐 안 거침)
.\.venv\Scripts\python.exe -m packages.subtitler.cli run <OPUS>

# 신청 적재 → 야간 드레인
.\.venv\Scripts\python.exe -m packages.subtitler.cli enqueue <OPUS>
.\.venv\Scripts\python.exe -m packages.subtitler.cli drain
```

```bash
# 외부 신청(API)
curl -X POST https://ai.kamoru.jk:8000/api/subtitle/requests \
     -H "Content-Type: application/json" -d '{"opus":"FSDSS-037"}'
```

---

## 품질·한계 (기대치 합의)

- 이 도메인은 대사가 적고 비발화 구간이 많아 **VAD 필터 필수**(없으면 무음에서 헛자막 — Whisper 환각).
  그래도 결과는 "방송 자막"이 아니라 **"대략의 뜻"** 수준. phase 1 단건으로 실제 영상에 돌려 판단.
- phase 1 번역은 NLLB(문장 단위) — 짧은 자막 조각은 문맥이 부족해 어색할 수 있다. phase 2 의
  LLM+번역메모리 few-shot 이 159개 팬자막 말투/용어에 맞춰 품질을 끌어올리는 단계다.
- 언어는 일본어 고정 가정. Whisper 가 다른 언어를 감지하면 note 로 남기되 번역은 JP 전제로 진행.

## 남은 작업 (phase 2/3)

- **phase 2 ① 번역메모리 (구현됨)**: `align.py`(시간정렬 + bge-m3 교차언어 유사도 필터) ·
  `tm.py`(전사→KO파싱→정렬→필터→`subtitle_tm`/`subtitle_corpus`) · CLI `build-tm [limit]`.
  증분(자막 mtime). 전체 137편 구축은 야간 1회(`build-tm`).
- **phase 2 ② LLM 번역 (구현됨)**: `translate.py mode="llm"` — `subtitle_tm` 을 bge-m3 로 임베딩
  (Qdrant `subtitle_tm` 컬렉션) → 번역할 JP 와 유사 예시 K개 검색 → 무검열 LLM(`translator_llm`,
  기본 `huihui_ai/qwen2.5-abliterate:14b`) 에 few-shot+용어집 주입, 세그먼트 12개씩 묶어 번역.
  깨진 줄(`_looks_bad`: 라틴 누출·한자 다수)은 NLLB 로 폴백. 프롬프트는 `prompts.py`(점잖은 기본값)
  + `subtitle_prompts.yaml`(gitignore 오버라이드, 예시 `subtitle_prompts.example.yaml`).
  실측(FSDSS-951 15세그먼트): NLLB 의 환각·오역·쓰레기를 LLM 이 교정 — 문맥·말투 대폭 개선 확인.
  `translator: "llm"` 로 켠다(기본은 아직 nllb — ③ 평가 후 전환 권장).
- **phase 2 ③ 평가 (다음)**: 일부 편을 TM 에서 제외(leakage 방지) → NLLB vs LLM+TM 을 사람 자막과
  chrF/LLM-judge 로 대조 → 모델·few-shot 수·청크 크기 결정.
- **phase 3 (싱크 수정)**: `core.resync()` — Whisper 발화구간을 앵커로 기존 KO 큐를 DTW 단조 정렬 후
  재타이밍. 사람 번역 텍스트는 보존, **타이밍만** 교정(챕터 경계 계단 드리프트 대응). 원본은 백업.
- 관리자 UI: 신청 큐/진행/이력 패널(`/stabilize` 페이지 패턴 재사용).
