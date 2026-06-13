# 일본어→한국어 번역 API (외부 시스템 연동 가이드)

> **대상 독자**: 이 번역 서비스를 호출해 개발하는 **타 시스템(및 그 시스템의 AI 에이전트)**.
> 이 문서 하나로 연동에 필요한 계약(요청/응답·제약·예시)을 모두 담는다. 코드 구현체는
> `apps/api/main.py`(`/api/translate` 라우트) + `packages/indexer/translate.py`.

## 1. 한 줄 요약

**일본어 텍스트를 한국어(또는 영어)로 번역**하는 단일 HTTP 엔드포인트. 로컬 NLLB-200 신경망
번역 + 품질 미달 시 LLM 폴백 + 결과 캐시. **완전 로컬(LAN)·인증 없음·자체 TLS.**

- **이 API가 하는 일**: `일본어 → 한국어`(기본), `일본어 → 영어`.
- **이 API가 하지 않는 일**: 한국어→일본어 등 **일본어를 목표 언어로 하는 번역은 미지원**
  (입력을 일본어로 가정. 비일본어 입력은 사실상 그대로 반환됨). 그쪽이 필요하면 별도 확장 필요.

## 2. 엔드포인트

| 항목 | 값 |
|---|---|
| 메서드·경로 | `POST /api/translate` |
| 베이스 URL | `https://ai.kamoru.jk:8000` |
| 전송 | TLS(**자체 서명 인증서**) — 클라이언트에서 인증서 검증 비활성 또는 CA 신뢰 필요 |
| 인증 | 없음 (LAN 전제, 인터넷 노출 금지) |
| Content-Type | `application/json` (**UTF-8 필수**) |

### 기계 판독 스펙 (에이전트가 직접 읽기 좋음)
- OpenAPI 3.1.0: `GET https://ai.kamoru.jk:8000/openapi.json`
- Swagger UI: `https://ai.kamoru.jk:8000/docs`

## 3. 요청 / 응답 계약

### 요청 본문 (`TranslateRequest`)
```jsonc
{
  "text": "今日はとても良い天気ですね。", // (필수) 번역할 일본어 원문
  "target": "ko",                        // (선택) "ko"(기본) | "en"
  "sentencewise": false                  // (선택) true 면 문장 단위로 쪼개 번역 후 결합
}
```

| 필드 | 타입 | 필수 | 기본 | 설명 |
|---|---|---|---|---|
| `text` | string | ✅ | — | 일본어 원문. 빈/공백 문자열이면 `""` 반환. |
| `target` | string | ❌ | `"ko"` | 목표 언어. `"ko"` 또는 `"en"`. 그 외 값은 `ko`로 취급. |
| `sentencewise` | boolean | ❌ | `false` | 긴 문단은 `true` 권장 — 문장 부호(`。．.!？?`)·줄바꿈 기준 분할 후 각각 번역. |

### 응답 (200)
```json
{ "text": "오늘 날씨가 아주 좋네요." }
```
단일 필드 `text`(번역문)만 반환.

### 동작 규칙 (중요)
- **소스 언어는 항상 일본어로 가정**(NLLB `src_lang=jpn_Jpan`). 한국어/영어 등을 넣으면 의미 있는
  번역이 아니라 **대체로 입력이 그대로 돌아온다**. 범용 번역기가 아님.
- **멱등 + 캐시**: 같은 `(text, target)` 재요청은 SQLite 캐시에서 즉시 반환(키 = `sha1(model|"ja"|target|text)`).
  타 시스템이 같은 문장을 반복 요청해도 비용이 거의 0.
- **길이 처리**: 단일 문자열은 입력 ~512 토큰에서 잘릴 수 있음. **여러 문장/긴 텍스트는 `sentencewise=true`**
  로 보내 문장별 번역을 권장.
- **품질 폴백**: NLLB 결과의 길이 비율이 비정상이거나 반복/언어 오염이 감지되면 자동으로 LLM(Qwen2.5)
  재번역 → 그래도 이상하면 원문(JP) 보존. 호출자는 별도 처리 불필요.

### 오류
| 상황 | 응답 |
|---|---|
| 본문이 JSON 파싱 불가/비UTF-8 | `422` `{"detail":"There was an error parsing the body"}` |
| `text` 누락 | `422` (검증 오류 상세) |

> **함정**: Windows `curl -d '…일본어…'` 는 비ASCII 본문을 깨뜨려 422가 난다. **UTF-8 파일
> (`--data-binary @body.json`) 또는 HTTP 라이브러리**를 쓸 것.

## 4. 호출 예시

### curl (UTF-8 파일 사용)
```bash
printf '{"text":"今日はとても良い天気ですね。","target":"ko"}' > body.json
curl -sk -X POST https://ai.kamoru.jk:8000/api/translate \
     -H "content-type: application/json" --data-binary @body.json
# → {"text":"오늘 날씨가 아주 좋네요."}
```

### Python
```python
import httpx
def translate_ja(text: str, target: str = "ko", sentencewise: bool = False) -> str:
    r = httpx.post(
        "https://ai.kamoru.jk:8000/api/translate",
        json={"text": text, "target": target, "sentencewise": sentencewise},
        verify=False,        # 자체 서명 인증서
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["text"]

print(translate_ja("今日はとても良い天気ですね。"))  # 오늘 날씨가 아주 좋네요.
```

### Node.js / TypeScript
```ts
async function translateJa(text: string, target: "ko" | "en" = "ko", sentencewise = false) {
  const res = await fetch("https://ai.kamoru.jk:8000/api/translate", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, target, sentencewise }),
  });
  if (!res.ok) throw new Error(`translate ${res.status}`);
  return (await res.json()).text as string;
}
// 주의: 자체 서명 인증서 → Node 는 NODE_TLS_REJECT_UNAUTHORIZED=0 또는 CA 등록 필요(개발 한정).
```

## 5. 브라우저(웹앱)에서 호출할 때 — CORS
서버-서버 호출은 CORS와 무관하다. **브라우저 자바스크립트**로 호출하려면 호출 페이지의 오리진이
서버 CORS 화이트리스트(`config.yaml: server.cors_origins`)에 있어야 한다. 현재 허용:
`https://ai.kamoru.jk:3000`, `http://ai.kamoru.jk:3000`, `http://localhost:3000`, `https://localhost:3000`.
새 웹앱 오리진은 운영자가 `cors_origins` 에 추가해야 한다.

## 6. 운영 전제 / 성능
- **첫 호출 지연**: 서버 기동 후 첫 번역은 NLLB 모델 로딩으로 수 초~수십 초. 이후는 빠름.
- **지연 가늠**: 캐시 히트 ≈ 즉시 / NLLB(GPU) ≈ 수백 ms~수 초 / LLM 폴백 ≈ 수 초.
- **인터넷 노출 금지**: LAN + 자체 TLS 전용. 외부 공개·민감정보 전송 금지.
- 서버는 GPU(RTX 4070 Ti)를 다른 작업과 공유하므로 대량 배치는 부하 경합 가능.

## 7. AI 에이전트 연동 체크리스트
1. 베이스 URL `https://ai.kamoru.jk:8000`, 경로 `POST /api/translate`.
2. 본문은 `{text, target?, sentencewise?}` — UTF-8 JSON, `content-type: application/json`.
3. 자체 서명 TLS → 검증 비활성(개발) 또는 CA 신뢰.
4. **입력은 일본어**라고 가정. 다른 언어 → 일본어 번역은 이 API로 불가.
5. 긴 텍스트는 `sentencewise=true`.
6. 동일 문장 반복 호출은 캐시로 저렴 — 클라이언트단 별도 캐시 불필요.
7. 응답은 `{"text": "..."}` 하나만 파싱.
8. 정확한 스키마가 필요하면 `/openapi.json`을 직접 읽어 코드 생성.
